"""
AutoTool 회계 ERP — Flask 앱 팩토리
별도 프로젝트로 개발 후 기존 autotool에 통합 예정.
"""
import os
import time
from flask import Flask, redirect, request, session, url_for, flash, jsonify
from flask_login import LoginManager, current_user, logout_user
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config, DevelopmentConfig


def create_app(config_class=None):
    app = Flask(__name__)

    if config_class is None:
        if os.environ.get('FLASK_ENV') == 'production':
            from config import ProductionConfig
            config_class = ProductionConfig
        else:
            config_class = DevelopmentConfig

    app.config.from_object(config_class)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    CSRFProtect(app)

    # ── DB 연결 ──
    from db_supabase import SupabaseDB
    db = SupabaseDB()
    db_url = app.config.get('SUPABASE_URL', '')
    db_key = app.config.get('SUPABASE_KEY', '')
    if db_url and db_key:
        if not db.connect(db_url, db_key):
            print("[WARN] Supabase 연결 실패 — DB URL/KEY를 확인하세요")
    else:
        print("[WARN] SUPABASE_URL / SUPABASE_KEY 미설정")
    app.db = db

    # ── CODEF 싱글톤 ──
    from services.codef_service import CodefService
    app.codef = CodefService(app.config)

    # ── Popbill 싱글톤 ──
    from services.popbill_service import PopbillService
    app.popbill = PopbillService(app.config)

    # ── Flask-Login ──
    from models import User
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '로그인이 필요합니다.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        try:
            row = app.db.query_user_by_id(int(user_id))
            return User(row) if row else None
        except Exception:
            return None

    # ── 세션 타임아웃 ──
    @app.before_request
    def check_session_timeout():
        if current_user.is_authenticated:
            now = time.time()
            last = session.get('_last_active', now)
            timeout_min = app.config.get('SESSION_INACTIVITY_TIMEOUT', 120)
            if now - last > timeout_min * 60:
                logout_user()
                session.clear()
                flash('세션이 만료되었습니다. 다시 로그인하세요.', 'warning')
                return redirect(url_for('auth.login'))
            session['_last_active'] = now
            session.permanent = True

    # ── 에러 핸들러 ──
    @app.errorhandler(CSRFError)
    def csrf_error(e):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'error': 'CSRF 토큰이 만료되었습니다. 페이지를 새로고침하세요.'}), 400
        flash('세션이 만료되었습니다. 다시 시도하세요.', 'warning')
        return redirect(request.referrer or url_for('accounting.dashboard'))

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'error': '페이지를 찾을 수 없습니다'}), 404
        flash('페이지를 찾을 수 없습니다.', 'warning')
        return redirect(url_for('accounting.dashboard'))

    @app.errorhandler(500)
    def server_error(e):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'error': '서버 오류가 발생했습니다'}), 500
        flash('서버 오류가 발생했습니다.', 'danger')
        return redirect(url_for('accounting.dashboard'))

    # ── 블루프린트 등록 ──
    from auth import auth_bp
    from blueprints.bank import bank_bp
    from blueprints.tax_invoice import tax_invoice_bp
    from blueprints.accounting import accounting_bp
    from blueprints.journal import journal_bp

    for bp in [auth_bp, bank_bp, tax_invoice_bp, accounting_bp, journal_bp]:
        app.register_blueprint(bp)

    # ── 메인 리다이렉트 ──
    @app.route('/')
    def root():
        if current_user.is_authenticated:
            return redirect(url_for('accounting.dashboard'))
        return redirect(url_for('auth.login'))

    # ── Jinja 필터 ──
    def fmt_money(val):
        """금액 포맷 (1,000,000)"""
        try:
            return f"{int(val):,}"
        except (ValueError, TypeError):
            return '0'

    def fmt_qty(val):
        try:
            n = float(val)
            return f"{int(n):,}" if n == int(n) else f"{n:,.2f}".rstrip('0').rstrip('.')
        except (ValueError, TypeError):
            return str(val) if val else '0'

    app.jinja_env.filters['fmt_money'] = fmt_money
    app.jinja_env.filters['fmt_qty'] = fmt_qty

    # ── context processor (사이드바 메뉴) ──
    @app.context_processor
    def inject_nav():
        nav_items = [
            {'name': '회계 대시보드', 'icon': 'bi-graph-up-arrow', 'url': '/accounting', 'group': '회계'},
            {'name': '은행 관리', 'icon': 'bi-bank', 'url': '/bank', 'group': '은행'},
            {'name': '거래내역', 'icon': 'bi-cash-stack', 'url': '/bank/transactions', 'group': '은행'},
            {'name': '세금계산서', 'icon': 'bi-receipt', 'url': '/tax-invoice', 'group': '세금계산서'},
            {'name': '세금계산서 발행', 'icon': 'bi-plus-circle', 'url': '/tax-invoice/issue', 'group': '세금계산서'},
            {'name': '매출-입금 매칭', 'icon': 'bi-link-45deg', 'url': '/accounting/matching', 'group': '매칭'},
            {'name': '미수금 관리', 'icon': 'bi-exclamation-triangle', 'url': '/accounting/receivables', 'group': '매칭'},
            {'name': '미지급금 관리', 'icon': 'bi-cash-coin', 'url': '/accounting/payables', 'group': '매칭'},
            {'name': '플랫폼 정산', 'icon': 'bi-shop', 'url': '/accounting/settlements', 'group': '정산'},
            {'name': '리포트', 'icon': 'bi-file-earmark-bar-graph', 'url': '/accounting/reports', 'group': '리포트'},
            {'name': '전표관리', 'icon': 'bi-journal-text', 'url': '/journal/', 'group': '회계'},
            {'name': '시산표', 'icon': 'bi-table', 'url': '/journal/trial-balance', 'group': '회계'},
        ]
        # 그룹별 분류
        groups = {}
        for item in nav_items:
            g = item['group']
            if g not in groups:
                groups[g] = []
            groups[g].append(item)

        return {
            'nav_groups': groups,
            'app_title': '회계 ERP',
        }

    # ── 디렉토리 생성 ──
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
    os.makedirs(app.config.get('OUTPUT_FOLDER', 'output'), exist_ok=True)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5002, debug=True)
