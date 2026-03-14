"""운영사 포털 — 대시보드, 과금(SaaS), 사용자관리."""
from flask import render_template
from flask_login import login_required, current_user

from . import operator_bp, _require_operator


# ═══ 대시보드 ═══

@operator_bp.route('/dashboard')
@login_required
@_require_operator
def dashboard():
    from db_utils import get_repo
    order_repo = get_repo('order')
    inv_repo = get_repo('inventory')
    client_repo = get_repo('client')

    order_counts = order_repo.count_by_status() or {}
    recent_orders = order_repo.get_recent_orders(limit=5) or []
    total_skus = inv_repo.count_skus() or 0
    low_stock = inv_repo.get_low_stock_items(threshold=10) or []
    clients = client_repo.list_clients() or []

    return render_template('operator/dashboard.html',
                           order_counts=order_counts,
                           recent_orders=recent_orders,
                           total_skus=total_skus,
                           low_stock_count=len(low_stock),
                           client_count=len(clients))


# ═══ 과금/청구 (SaaS 플랜) ═══

@operator_bp.route('/billing')
@login_required
@_require_operator
def billing():
    from db_utils import get_repo
    repo = get_repo('billing')
    plans = repo.list_plans()
    invoices = repo.list_invoices()
    usage = repo.list_usage()
    return render_template('operator/billing.html', plans=plans, invoices=invoices,
                           usage=usage)


# ═══ 사용자관리 ═══

@operator_bp.route('/users')
@login_required
@_require_operator
def users():
    if not current_user.is_admin():
        from flask import abort
        abort(403)
    from db_utils import get_repo
    repo = get_repo('user')
    items = repo.list_users()
    pending = repo.list_pending_approvals()
    return render_template('operator/users.html', users=items, pending=pending)


@operator_bp.route('/users/<int:user_id>/approve', methods=['POST'])
@login_required
@_require_operator
def user_approve(user_id):
    if not current_user.is_admin():
        from flask import abort
        abort(403)
    from db_utils import get_repo
    from flask import redirect, url_for, flash
    repo = get_repo('user')
    repo.approve_user(user_id)
    flash('사용자가 승인되었습니다.', 'success')
    return redirect(url_for('operator.users'))
