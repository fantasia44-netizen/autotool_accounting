"""3PL SaaS 설정 — 환경변수 기반."""
import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

    # 세션
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400  # 24h

    # 파일 업로드
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

    # 세션 비활동 타임아웃 (분)
    SESSION_INACTIVITY_TIMEOUT = 60  # 개발: 60분

    # 로그인 보안
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_LOCKOUT_MINUTES = 15
    IP_RATE_LIMIT_ATTEMPTS = 20
    IP_RATE_LIMIT_WINDOW = 900  # 15분
    IP_RATE_LIMIT_BLOCK_DURATION = 1800  # 30분

    # 앱 모드
    APP_NAME = 'PackFlow'
    APP_MODE = os.environ.get('APP_MODE', '3pl')
    TEST_MODE = os.environ.get('TEST_MODE', '') == '1'

    # ── UTF-8 인코딩 (한글 깨짐 방지) ──
    JSON_AS_ASCII = False  # jsonify()에서 한글 그대로 출력
    JSONIFY_MIMETYPE = 'application/json; charset=utf-8'


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_INACTIVITY_TIMEOUT = 120  # 프로덕션: 2시간
    LOGIN_MAX_ATTEMPTS = 3  # 프로덕션은 더 엄격
