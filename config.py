import os
from datetime import timedelta
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

# Supabase (기존 autotool과 동일 DB)
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()

    SUPABASE_URL = SUPABASE_URL
    SUPABASE_KEY = SUPABASE_KEY

    # 세션 보안
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_INACTIVITY_TIMEOUT = 120  # 2시간

    # ── CODEF (코드에프) 설정 ──
    CODEF_DEMO_CLIENT_ID = os.environ.get('CODEF_DEMO_CLIENT_ID', '')
    CODEF_DEMO_CLIENT_SECRET = os.environ.get('CODEF_DEMO_CLIENT_SECRET', '')
    CODEF_CLIENT_ID = os.environ.get('CODEF_CLIENT_ID', '')
    CODEF_CLIENT_SECRET = os.environ.get('CODEF_CLIENT_SECRET', '')
    CODEF_PUBLIC_KEY = os.environ.get('CODEF_PUBLIC_KEY', '')
    CODEF_IS_TEST = os.environ.get('CODEF_IS_TEST', 'true').lower() == 'true'
    CODEF_MODE = os.environ.get('CODEF_MODE', 'sandbox')  # sandbox/demo/product
    CODEF_CORP_NUM = os.environ.get('CODEF_CORP_NUM', '')  # 해서물산 법인 사업자번호

    # ── Popbill (팝빌) 설정 ──
    POPBILL_LINK_ID = os.environ.get('POPBILL_LINK_ID', 'TESTER')
    POPBILL_SECRET_KEY = os.environ.get('POPBILL_SECRET_KEY', '')
    POPBILL_IS_TEST = os.environ.get('POPBILL_IS_TEST', 'true').lower() == 'true'
    POPBILL_IP_RESTRICT = False   # Render 유동 IP 대응
    POPBILL_CORP_NUM = os.environ.get('POPBILL_CORP_NUM', '')  # 우리 사업자번호

    # 역할 (기존 autotool 호환)
    ROLES = {
        'admin': {'name': '관리자', 'level': 100},
        'ceo': {'name': '대표', 'level': 90},
        'manager': {'name': '총괄책임자', 'level': 80},
        'sales': {'name': '영업부', 'level': 50},
        'logistics': {'name': '물류팀', 'level': 50},
        'production': {'name': '생산부', 'level': 50},
        'general': {'name': '총무부', 'level': 50},
    }

    # 로그인 시도 제한
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_LOCKOUT_MINUTES = 15
    IP_RATE_LIMIT_ATTEMPTS = 20
    IP_RATE_LIMIT_WINDOW = 900
    IP_RATE_LIMIT_BLOCK_DURATION = 1800

    # 파일
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    OUTPUT_FOLDER = os.path.join(basedir, 'output')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PREFERRED_URL_SCHEME = 'https'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_INACTIVITY_TIMEOUT = 120
    LOGIN_MAX_ATTEMPTS = 3
    IP_RATE_LIMIT_ATTEMPTS = 10
