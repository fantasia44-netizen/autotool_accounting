"""3PL SaaS — Flask Application Factory."""
import os
from flask import Flask, g, session

try:
    from supabase import create_client
except ImportError:
    create_client = None  # supabase 미설치 시 데모 모드 전용

from config import Config, DevelopmentConfig, ProductionConfig
from models import User


def create_app(config_class=None):
    """Flask 앱 팩토리."""
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')

    # 설정
    if config_class is None:
        env = os.environ.get('FLASK_ENV', 'development')
        config_class = ProductionConfig if env == 'production' else DevelopmentConfig
    app.config.from_object(config_class)

    # Supabase 클라이언트
    url = app.config['SUPABASE_URL']
    key = app.config['SUPABASE_KEY']
    if url and key and create_client:
        app.supabase = create_client(url, key)
    else:
        app.supabase = None

    # ── Extensions ──
    _init_csrf(app)
    _init_login(app)
    _init_repositories(app)
    _register_blueprints(app)
    _register_hooks(app)

    # 랜딩 페이지 (비로그인 시) / 포털 리다이렉트 (로그인 시)
    @app.route('/')
    def index():
        from flask import redirect, url_for, render_template
        from flask_login import current_user
        if current_user.is_authenticated:
            portal = current_user.get_portal()
            return redirect(url_for(f'{portal}.dashboard'))
        return render_template('landing/index.html')

    return app


def _init_csrf(app):
    """CSRF 보호 초기화 (Flask-WTF)."""
    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)
    app.csrf = csrf


def _init_login(app):
    """Flask-Login 초기화."""
    from flask_login import LoginManager
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        # 데모 모드: 세션에서 사용자 복원
        if not app.supabase:
            from flask import session as flask_session
            demo_user = flask_session.get('demo_user')
            if demo_user and str(demo_user.get('id')) == str(user_id):
                return User(demo_user)
            return None
        res = app.supabase.table('users').select('*').eq(
            'id', int(user_id)
        ).execute()
        if res.data:
            return User(res.data[0])
        return None


def _init_repositories(app):
    """Repository 인스턴스를 app에 등록."""
    from repositories.warehouse_repo import WarehouseRepository
    from repositories.inventory_repo import InventoryRepository
    from repositories.order_repo import OrderRepository
    from repositories.billing_repo import BillingRepository
    from repositories.packing_repo import PackingRepository
    from repositories.client_repo import ClientRepository
    from repositories.user_repo import UserRepository
    from repositories.client_rate_repo import ClientRateRepository
    from repositories.picking_repo import PickingRepository
    from repositories.client_marketplace_repo import ClientMarketplaceRepository
    from repositories.client_billing_repo import ClientBillingRepository

    app.repos = {
        'warehouse': WarehouseRepository,
        'inventory': InventoryRepository,
        'order': OrderRepository,
        'billing': BillingRepository,
        'packing': PackingRepository,
        'client': ClientRepository,
        'user': UserRepository,
        'client_rate': ClientRateRepository,
        'picking': PickingRepository,
        'client_marketplace': ClientMarketplaceRepository,
        'client_billing': ClientBillingRepository,
    }


def _register_blueprints(app):
    """블루프린트 등록."""
    from blueprints.operator import operator_bp
    from blueprints.client.views import client_bp
    from blueprints.packing.views import packing_bp
    from blueprints.api.views import api_bp
    from auth import auth_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(operator_bp, url_prefix='/operator')
    app.register_blueprint(client_bp, url_prefix='/client')
    app.register_blueprint(packing_bp, url_prefix='/packing')
    app.register_blueprint(api_bp, url_prefix='/api/v1')

    # API 블루프린트는 CSRF 면제 (토큰 인증 사용)
    if hasattr(app, 'csrf'):
        app.csrf.exempt(api_bp)


def _register_hooks(app):
    """before_request / context_processor 등록."""

    @app.before_request
    def set_tenant():
        """요청별 operator_id 기반 repository 인스턴스 주입."""
        from flask_login import current_user
        g.operator_id = None
        if hasattr(current_user, 'operator_id') and current_user.operator_id:
            g.operator_id = current_user.operator_id

    @app.after_request
    def set_utf8_headers(response):
        """모든 HTML/JSON 응답에 UTF-8 charset 강제."""
        ct = response.content_type or ''
        if 'text/html' in ct and 'charset' not in ct:
            response.content_type = 'text/html; charset=utf-8'
        return response

    # ── Jinja 글로벌 함수 (템플릿에서 직접 호출 가능) ──
    from services.tz_utils import now_kst, today_kst, format_kst
    app.jinja_env.globals['now_kst'] = now_kst
    app.jinja_env.globals['today_kst'] = today_kst
    app.jinja_env.globals['format_kst'] = format_kst

    @app.context_processor
    def inject_globals():
        """템플릿 전역 변수 + 동적 메뉴."""
        from flask_login import current_user
        from models import get_menu_for_user, ROLES
        menu_groups = []
        role_label = ''
        if hasattr(current_user, 'role') and current_user.is_authenticated:
            menu_groups = get_menu_for_user(current_user)
            role_label = ROLES.get(current_user.role, {}).get('label', current_user.role)
        return {
            'app_name': 'PackFlow',
            'app_mode': app.config.get('APP_MODE', '3pl'),
            'menu_groups': menu_groups,
            'role_label': role_label,
            'test_mode': os.environ.get('TEST_MODE', '') == '1',
        }
