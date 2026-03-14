"""3PL SaaS — 인증 블루프린트."""
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import User

auth_bp = Blueprint('auth', __name__, template_folder='templates')

# ── 로컬 데모 사용자 (Supabase 없이 테스트) ──
DEMO_USERS = {
    'admin': {'id': 1, 'username': 'admin', 'password_hash': 'test1234', 'name': '김관리',
              'role': 'admin', 'operator_id': 1, 'client_id': None, 'is_approved': True},
    'manager': {'id': 2, 'username': 'manager', 'password_hash': 'test1234', 'name': '박매니저',
                'role': 'manager', 'operator_id': 1, 'client_id': None, 'is_approved': True},
    'client1': {'id': 4, 'username': 'client1', 'password_hash': 'test1234', 'name': '정화주A',
                'role': 'client_admin', 'operator_id': 1, 'client_id': 1, 'is_approved': True},
    'client2': {'id': 5, 'username': 'client2', 'password_hash': 'test1234', 'name': '한화주B',
                'role': 'client_admin', 'operator_id': 1, 'client_id': 2, 'is_approved': True},
    'packer1': {'id': 6, 'username': 'packer1', 'password_hash': 'test1234', 'name': '강패커',
                'role': 'packing_lead', 'operator_id': 1, 'client_id': None, 'is_approved': True},
    'packer2': {'id': 7, 'username': 'packer2', 'password_hash': 'test1234', 'name': '윤작업',
                'role': 'packing_worker', 'operator_id': 1, 'client_id': None, 'is_approved': True},
}


def _is_demo_mode():
    """Supabase 미연결 시 데모 모드."""
    return not current_app.supabase


def _get_test_mode():
    return os.environ.get('TEST_MODE', '') == '1'


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return _redirect_by_portal(current_user)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('아이디와 비밀번호를 입력하세요.', 'warning')
            return render_template('login.html', test_mode=_get_test_mode(),
                                   demo_mode=_is_demo_mode())

        # ── 데모 모드: 로컬 사용자로 로그인 ──
        if _is_demo_mode():
            demo_user = DEMO_USERS.get(username)
            if not demo_user or demo_user['password_hash'] != password:
                flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'danger')
                return render_template('login.html', test_mode=_get_test_mode(),
                                       demo_mode=True)
            user = User(demo_user)
            login_user(user, remember=True)
            # 세션에 데모 유저 정보 저장 (user_loader용)
            session['demo_user'] = demo_user
            return _redirect_by_portal(user)

        # ── 실제 모드: Supabase 조회 ──
        db = current_app.supabase
        res = db.table('users').select('*').eq('username', username).execute()
        if not res.data:
            flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'danger')
            return render_template('login.html', test_mode=_get_test_mode())

        row = res.data[0]
        # TODO: bcrypt 비밀번호 검증 추가
        if row.get('password_hash') != password:
            flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'danger')
            return render_template('login.html', test_mode=_get_test_mode())

        if not row.get('is_approved'):
            flash('계정 승인 대기 중입니다.', 'warning')
            return render_template('login.html', test_mode=_get_test_mode())

        user = User(row)
        login_user(user, remember=True)
        return _redirect_by_portal(user)

    return render_template('login.html', test_mode=_get_test_mode(),
                           demo_mode=_is_demo_mode())


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('auth.login'))


def _redirect_by_portal(user):
    """역할에 따른 포털 리다이렉트."""
    portal = user.get_portal()
    if portal == 'client':
        return redirect(url_for('client.dashboard'))
    elif portal == 'packing':
        return redirect(url_for('packing.dashboard'))
    return redirect(url_for('operator.dashboard'))
