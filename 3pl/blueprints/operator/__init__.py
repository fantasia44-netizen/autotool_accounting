"""운영사 포털 Blueprint — 도메인별 모듈 분리."""
from flask import Blueprint
from flask_login import current_user
from functools import wraps

operator_bp = Blueprint('operator', __name__)


def _require_operator(f):
    """운영사 역할 체크 데코레이터."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_operator():
            from flask import abort
            abort(403)
        return f(*args, **kwargs)
    return decorated


# 도메인별 라우트 모듈 로드 (Blueprint에 라우트 등록)
from . import order_views      # noqa: F401,E402 — 주문/출고/피킹/패킹
from . import inventory_views  # noqa: F401,E402 — 재고/입고/조정/수불부/SKU
from . import client_views     # noqa: F401,E402 — 고객사/요금/마켓플레이스/과금
from . import warehouse_views  # noqa: F401,E402 — 창고/존/로케이션
from . import views            # noqa: F401,E402 — 대시보드/과금/사용자 (기존 잔여)
