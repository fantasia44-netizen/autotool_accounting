"""고객사 포털 — 재고조회, 주문현황, 출고영상."""
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from functools import wraps

client_bp = Blueprint('client', __name__)


def _require_client(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_client():
            from flask import abort
            abort(403)
        return f(*args, **kwargs)
    return decorated


@client_bp.route('/dashboard')
@login_required
@_require_client
def dashboard():
    from db_utils import get_repo
    order_repo = get_repo('order')
    inv_repo = get_repo('inventory')

    orders = order_repo.list_orders(client_id=current_user.client_id, limit=5) or []
    order_counts = order_repo.count_by_status() or {}
    skus = inv_repo.list_skus(client_id=current_user.client_id) or []
    stocks = inv_repo.list_all_stock() or []

    return render_template('client/dashboard.html',
                           orders=orders,
                           order_counts=order_counts,
                           skus=skus,
                           stocks=stocks)


@client_bp.route('/inventory')
@login_required
@_require_client
def inventory():
    from db_utils import get_repo
    inv_repo = get_repo('inventory')
    skus = inv_repo.list_skus(client_id=current_user.client_id)
    stocks = inv_repo.list_all_stock()
    return render_template('client/inventory.html', skus=skus, stocks=stocks)


@client_bp.route('/orders')
@login_required
@_require_client
def orders():
    from db_utils import get_repo
    repo = get_repo('order')
    status = request.args.get('status')
    items = repo.list_orders(client_id=current_user.client_id, status=status)
    counts = repo.count_by_status()
    return render_template('client/orders.html', orders=items, counts=counts,
                           filter_status=status)


@client_bp.route('/videos')
@login_required
@_require_client
def videos():
    from db_utils import get_repo
    packing_repo = get_repo('packing')
    jobs = packing_repo.list_jobs(status='completed')
    return render_template('client/videos.html', jobs=jobs)
