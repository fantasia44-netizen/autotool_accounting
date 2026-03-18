"""3PL SaaS — Flask Application Factory."""
import os
import time
from flask import Flask, g, session, redirect, url_for, flash, request, jsonify

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
    from repositories.audit_repo import AuditRepository
    from repositories.finance_repo import FinanceRepository

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
        'audit': AuditRepository,
        'finance': FinanceRepository,
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
    """before_request / after_request / errorhandler 등록."""
    from flask_login import current_user, logout_user
    from flask_wtf.csrf import CSRFError

    # ── before_request ──

    @app.before_request
    def check_session_timeout():
        """세션 비활동 타임아웃 — 초과 시 자동 로그아웃."""
        if current_user.is_authenticated:
            now = time.time()
            last_active = session.get('_last_active', now)
            timeout_min = app.config.get('SESSION_INACTIVITY_TIMEOUT', 60)
            if now - last_active > timeout_min * 60:
                logout_user()
                session.clear()
                if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': '세션 만료'}), 401
                flash('비활동으로 자동 로그아웃되었습니다.', 'warning')
                return redirect(url_for('auth.login'))
            session['_last_active'] = now

    @app.before_request
    def enforce_https():
        """프로덕션 HTTPS 강제 리다이렉트."""
        if app.config.get('SESSION_COOKIE_SECURE'):
            if request.headers.get('X-Forwarded-Proto', 'https') == 'http':
                url = request.url.replace('http://', 'https://', 1)
                return redirect(url, code=301)

    @app.before_request
    def set_tenant():
        """요청별 operator_id 기반 repository 인스턴스 주입."""
        g.operator_id = None
        if hasattr(current_user, 'operator_id') and current_user.operator_id:
            g.operator_id = current_user.operator_id

    # ── after_request ──

    @app.after_request
    def set_utf8_headers(response):
        """UTF-8 charset 강제 + 보안 헤더."""
        ct = response.content_type or ''
        if 'text/html' in ct and 'charset' not in ct:
            response.content_type = 'text/html; charset=utf-8'
        # 보안 헤더
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if current_user.is_authenticated:
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
        return response

    # ── 전역 에러 핸들러 ──

    def _is_api_request():
        return (request.is_json
                or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                or request.path.startswith('/api/'))

    @app.errorhandler(400)
    def handle_400(e):
        if _is_api_request():
            return jsonify({'error': '잘못된 요청입니다.'}), 400
        flash('잘못된 요청입니다.', 'danger')
        return redirect(request.referrer or url_for('index'))

    @app.errorhandler(403)
    def handle_403(e):
        if _is_api_request():
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        flash('접근 권한이 없습니다.', 'danger')
        return redirect(request.referrer or url_for('index'))

    @app.errorhandler(404)
    def handle_404(e):
        # 정적 리소스는 flash 없이 처리
        static_ext = ('.ico', '.css', '.js', '.png', '.jpg', '.gif', '.svg', '.woff', '.woff2', '.ttf', '.map')
        if request.path.endswith(static_ext):
            return '', 404
        if _is_api_request():
            return jsonify({'error': '요청한 리소스를 찾을 수 없습니다.'}), 404
        flash('페이지를 찾을 수 없습니다.', 'warning')
        return redirect(url_for('index'))

    @app.errorhandler(500)
    def handle_500(e):
        if _is_api_request():
            return jsonify({'error': '서버 내부 오류가 발생했습니다.'}), 500
        flash('서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.', 'danger')
        return redirect(url_for('index'))

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if _is_api_request():
            return jsonify({'error': '세션이 만료되었습니다. 페이지를 새로고침 해주세요.'}), 400
        flash('세션이 만료되었습니다. 페이지를 새로고침 해주세요.', 'warning')
        return redirect(request.referrer or url_for('auth.login'))

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
