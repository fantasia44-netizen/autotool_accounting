"""3PL SaaS — 인증 블루프린트."""
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from models import User

auth_bp = Blueprint('auth', __name__, template_folder='templates')

# ── IP Rate Limiting ──
_IP_MAX_ATTEMPTS = 20        # IP당 최대 시도 횟수
_IP_WINDOW_SEC = 15 * 60     # 15분 윈도우
_IP_BLOCK_SEC = 30 * 60      # 30분 차단

_ip_login_attempts = defaultdict(list)   # {ip: [timestamp, ...]}
_ip_blocked_until = {}                    # {ip: blocked_until_timestamp}

# ── 계정 잠금 설정 ──
_ACCOUNT_MAX_FAILURES = 5
_ACCOUNT_LOCK_MIN = 15

# ── 로컬 데모 사용자 (Supabase 없이 테스트) ──
_DEMO_PW_HASH = 'scrypt:32768:8:1$BZDB9O5vMy7KgVBQ$d64d2a693115f7844ac72ea27a905d225916a059d53445f35549c216d6846dc7ab6663ea1bc64fb72d21616adf051d2bf715e41a55f9a135173e137ae7a8ee24'

DEMO_USERS = {
    'admin': {'id': 1, 'username': 'admin', 'password_hash': _DEMO_PW_HASH, 'name': '김관리',
              'role': 'admin', 'operator_id': 1, 'client_id': None, 'is_approved': True},
    'manager': {'id': 2, 'username': 'manager', 'password_hash': _DEMO_PW_HASH, 'name': '박매니저',
                'role': 'manager', 'operator_id': 1, 'client_id': None, 'is_approved': True},
    'client1': {'id': 4, 'username': 'client1', 'password_hash': _DEMO_PW_HASH, 'name': '정화주A',
                'role': 'client_admin', 'operator_id': 1, 'client_id': 1, 'is_approved': True},
    'client2': {'id': 5, 'username': 'client2', 'password_hash': _DEMO_PW_HASH, 'name': '한화주B',
                'role': 'client_admin', 'operator_id': 1, 'client_id': 2, 'is_approved': True},
    'packer1': {'id': 6, 'username': 'packer1', 'password_hash': _DEMO_PW_HASH, 'name': '강패커',
                'role': 'packing_lead', 'operator_id': 1, 'client_id': None, 'is_approved': True},
    'packer2': {'id': 7, 'username': 'packer2', 'password_hash': _DEMO_PW_HASH, 'name': '윤작업',
                'role': 'packing_worker', 'operator_id': 1, 'client_id': None, 'is_approved': True},
}


# ── IP Rate Limit 함수 ──

def _check_ip_rate_limit(ip):
    """차단 중이면 남은 초 반환, 통과 시 0."""
    blocked = _ip_blocked_until.get(ip)
    if blocked:
        remaining = blocked - time.time()
        if remaining > 0:
            return int(remaining)
        # 차단 해제
        del _ip_blocked_until[ip]
        _ip_login_attempts.pop(ip, None)
    return 0


def _record_ip_attempt(ip):
    """시도 기록, 제한 초과 시 차단 설정."""
    now = time.time()
    attempts = _ip_login_attempts[ip]
    # 윈도우 밖 기록 제거
    cutoff = now - _IP_WINDOW_SEC
    _ip_login_attempts[ip] = [t for t in attempts if t > cutoff]
    _ip_login_attempts[ip].append(now)

    if len(_ip_login_attempts[ip]) > _IP_MAX_ATTEMPTS:
        _ip_blocked_until[ip] = now + _IP_BLOCK_SEC


# ── 감사 로그 ──

def _write_audit_log(db, username, action, ip, detail=None):
    """audit_logs 테이블에 로그 기록."""
    try:
        db.table('audit_logs').insert({
            'username': username,
            'action': action,
            'ip_address': ip,
            'detail': detail or '',
            'created_at': datetime.utcnow().isoformat(),
        }).execute()
    except Exception:
        # 감사 로그 실패가 로그인 자체를 막지 않도록
        current_app.logger.warning(f'audit_log insert failed: {username}/{action}')


# ── 계정 잠금 함수 ──

def _check_account_lock(row):
    """계정 잠금 상태 확인. 잠겨 있으면 True."""
    locked_until = row.get('locked_until')
    if not locked_until:
        return False
    if isinstance(locked_until, str):
        try:
            locked_until = datetime.fromisoformat(locked_until.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return False
    if isinstance(locked_until, datetime):
        if locked_until.tzinfo:
            now = datetime.now(locked_until.tzinfo)
        else:
            now = datetime.utcnow()
        if locked_until > now:
            return True
    return False


def _increment_failed_login(db, user_id, failed_count):
    """실패 횟수 증가, 임계치 초과 시 잠금 설정."""
    new_count = (failed_count or 0) + 1
    update_data = {'failed_login_count': new_count}
    if new_count >= _ACCOUNT_MAX_FAILURES:
        lock_until = datetime.utcnow() + timedelta(minutes=_ACCOUNT_LOCK_MIN)
        update_data['locked_until'] = lock_until.isoformat()
    try:
        db.table('app_users').update(update_data).eq('id', user_id).execute()
    except Exception:
        current_app.logger.warning(f'failed_login_count update failed: user_id={user_id}')


def _reset_failed_login(db, user_id):
    """로그인 성공 시 실패 카운터 리셋."""
    try:
        db.table('app_users').update({
            'failed_login_count': 0,
            'locked_until': None,
        }).eq('id', user_id).execute()
    except Exception:
        current_app.logger.warning(f'failed_login reset failed: user_id={user_id}')


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
        company_code = request.form.get('company_code', '').strip().upper()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        client_ip = request.remote_addr or '0.0.0.0'

        if not company_code or not username or not password:
            flash('회사코드, 아이디, 비밀번호를 모두 입력하세요.', 'warning')
            return render_template('login.html', test_mode=_get_test_mode(),
                                   demo_mode=_is_demo_mode(), company_code=company_code)

        # ── IP Rate Limit 체크 ──
        blocked_sec = _check_ip_rate_limit(client_ip)
        if blocked_sec > 0:
            flash(f'너무 많은 로그인 시도입니다. {blocked_sec // 60}분 후 다시 시도하세요.', 'danger')
            return render_template('login.html', test_mode=_get_test_mode(),
                                   demo_mode=_is_demo_mode())

        # ── 데모 모드: 로컬 사용자로 로그인 ──
        if _is_demo_mode():
            demo_user = DEMO_USERS.get(username)
            if not demo_user or not check_password_hash(demo_user['password_hash'], password):
                _record_ip_attempt(client_ip)
                flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'danger')
                return render_template('login.html', test_mode=_get_test_mode(),
                                       demo_mode=True, company_code=company_code)
            user = User(demo_user)
            login_user(user, remember=True)
            session['demo_user'] = demo_user
            return _redirect_by_portal(user)

        # ── 실제 모드: 회사코드로 operator 조회 → 해당 operator의 user 조회 ──
        db = current_app.supabase

        # 1) 회사코드로 운영사 찾기
        op_res = db.table('operators').select('id,name,company_code,is_active').eq(
            'company_code', company_code).execute()
        if not op_res.data:
            _record_ip_attempt(client_ip)
            flash('존재하지 않는 회사코드입니다.', 'danger')
            return render_template('login.html', test_mode=_get_test_mode(),
                                   company_code=company_code)
        operator = op_res.data[0]
        if not operator.get('is_active', True):
            flash('비활성화된 운영사입니다. 관리자에게 문의하세요.', 'danger')
            return render_template('login.html', test_mode=_get_test_mode(),
                                   company_code=company_code)

        # 2) 해당 운영사의 사용자 조회
        res = db.table('app_users').select('*').eq('username', username).eq(
            'operator_id', operator['id']).execute()
        if not res.data:
            _record_ip_attempt(client_ip)
            _write_audit_log(db, username, 'login_fail', client_ip,
                             f'회사코드={company_code}, 존재하지 않는 계정')
            flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'danger')
            return render_template('login.html', test_mode=_get_test_mode(),
                                   company_code=company_code)

        row = res.data[0]

        # ── 계정 잠금 체크 ──
        if _check_account_lock(row):
            _write_audit_log(db, username, 'login_blocked', client_ip, '계정 잠금 상태')
            flash('계정이 잠겼습니다. 잠시 후 다시 시도하세요.', 'danger')
            return render_template('login.html', test_mode=_get_test_mode(),
                                   company_code=company_code)

        # ── 비밀번호 검증 (해시) ──
        if not check_password_hash(row.get('password_hash', ''), password):
            _record_ip_attempt(client_ip)
            _increment_failed_login(db, row['id'], row.get('failed_login_count', 0))
            _write_audit_log(db, username, 'login_fail', client_ip, '비밀번호 불일치')
            flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'danger')
            return render_template('login.html', test_mode=_get_test_mode(),
                                   company_code=company_code)

        if not row.get('is_approved'):
            flash('계정 승인 대기 중입니다.', 'warning')
            return render_template('login.html', test_mode=_get_test_mode(),
                                   company_code=company_code)

        # ── 로그인 성공 ──
        _reset_failed_login(db, row['id'])
        _write_audit_log(db, username, 'login_success', client_ip)
        user = User(row)
        login_user(user, remember=True)
        return _redirect_by_portal(user)

    return render_template('login.html', test_mode=_get_test_mode(),
                           demo_mode=_is_demo_mode(),
                           company_code=request.args.get('code', ''))


@auth_bp.route('/join', methods=['GET'])
@auth_bp.route('/join/<company_code>', methods=['GET'])
def join_info(company_code=None):
    """직원 가입 안내 / 가입 폼 페이지."""
    operator = None
    if company_code and not _is_demo_mode():
        db = current_app.supabase
        if db:
            res = db.table('operators').select('id,name,company_code,is_active').eq(
                'company_code', company_code.upper()).execute()
            if res.data and res.data[0].get('is_active', True):
                operator = res.data[0]
    return render_template('join.html', company_code=company_code or '',
                           operator=operator, demo_mode=_is_demo_mode())


@auth_bp.route('/join/register', methods=['POST'])
def join_register():
    """직원 가입 처리."""
    if _is_demo_mode():
        flash('데모 모드에서는 가입할 수 없습니다.', 'warning')
        return redirect(url_for('auth.join_info'))

    company_code = request.form.get('company_code', '').strip().upper()
    username = request.form.get('username', '').strip()
    name = request.form.get('name', '').strip()
    password = request.form.get('password', '').strip()
    password_confirm = request.form.get('password_confirm', '').strip()
    phone = request.form.get('phone', '').strip()

    if not all([company_code, username, name, password]):
        flash('모든 필수 항목을 입력하세요.', 'warning')
        return redirect(url_for('auth.join_info', company_code=company_code))

    if password != password_confirm:
        flash('비밀번호가 일치하지 않습니다.', 'danger')
        return redirect(url_for('auth.join_info', company_code=company_code))

    if len(password) < 6:
        flash('비밀번호는 6자 이상이어야 합니다.', 'danger')
        return redirect(url_for('auth.join_info', company_code=company_code))

    db = current_app.supabase
    # 회사코드로 운영사 조회
    op_res = db.table('operators').select('id,name,is_active').eq(
        'company_code', company_code).execute()
    if not op_res.data:
        flash('존재하지 않는 회사코드입니다.', 'danger')
        return redirect(url_for('auth.join_info', company_code=company_code))
    operator = op_res.data[0]
    if not operator.get('is_active', True):
        flash('비활성화된 운영사입니다.', 'danger')
        return redirect(url_for('auth.join_info', company_code=company_code))

    # 중복 체크 (같은 운영사 내 같은 username)
    dup_res = db.table('app_users').select('id').eq('username', username).eq(
        'operator_id', operator['id']).execute()
    if dup_res.data:
        flash('이미 사용 중인 아이디입니다.', 'danger')
        return redirect(url_for('auth.join_info', company_code=company_code))

    # 가입 (승인 대기 상태)
    from werkzeug.security import generate_password_hash
    db.table('app_users').insert({
        'username': username,
        'password_hash': generate_password_hash(password),
        'name': name,
        'role': 'viewer',
        'operator_id': operator['id'],
        'phone': phone or None,
        'is_approved': False,
        'is_active': True,
    }).execute()

    flash(f'가입 신청 완료! "{operator["name"]}" 관리자의 승인을 기다려주세요.', 'success')
    return redirect(url_for('auth.login', code=company_code))


@auth_bp.route('/logout')
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('auth.login'))


def _redirect_by_portal(user):
    """역할에 따른 포털 리다이렉트."""
    portal = user.get_portal()
    if portal == 'client':
        return redirect(url_for('client.dashboard'))
    elif portal == 'packing':
        return redirect(url_for('packing.dashboard'))
    return redirect(url_for('operator.dashboard'))
