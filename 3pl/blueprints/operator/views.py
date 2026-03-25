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
    from datetime import datetime, timezone
    from services.cache import dashboard_cache

    op_id = current_user.operator_id or 0
    cache_key = f'op_dash:{op_id}'

    # 캐시 히트 시 즉시 반환 (TTL 45초)
    cached = dashboard_cache.get(cache_key)
    if cached:
        return render_template('operator/dashboard.html', **cached)

    order_repo = get_repo('order')
    inv_repo = get_repo('inventory')
    client_repo = get_repo('client')
    billing_repo = get_repo('client_billing')

    order_counts = order_repo.count_by_status() or {}
    recent_orders = order_repo.get_recent_orders(limit=5) or []
    total_skus = inv_repo.count_skus() or 0
    low_stock = inv_repo.get_low_stock_items(threshold=10) or []
    expiring_soon = inv_repo.get_expiring_soon(days=7) or []
    clients = client_repo.list_clients() or []

    # KPI: 출고 처리량
    shipped_count = order_counts.get('shipped', 0) + order_counts.get('delivered', 0)
    total_orders = sum(order_counts.values()) if order_counts else 0
    pending_orders = order_counts.get('pending', 0) + order_counts.get('confirmed', 0)

    # KPI: 클라이언트별 월매출 — 1회 일괄 조회 (N+1 제거)
    ym = datetime.now(timezone.utc).strftime('%Y-%m')
    bulk_totals = billing_repo.get_bulk_monthly_totals(ym) or {}
    client_revenue = {}
    for c in clients:
        cid = c['id']
        total = bulk_totals.get(cid, 0)
        client_revenue[cid] = {
            'name': c.get('company_name', c.get('name', '')),
            'total': total,
        }
    monthly_total = sum(v['total'] for v in client_revenue.values())

    ctx = dict(
        order_counts=order_counts,
        recent_orders=recent_orders,
        total_skus=total_skus,
        low_stock=low_stock,
        low_stock_count=len(low_stock),
        expiring_soon_count=len(expiring_soon),
        client_count=len(clients),
        shipped_count=shipped_count,
        total_orders=total_orders,
        pending_orders=pending_orders,
        client_revenue=client_revenue,
        monthly_total=monthly_total,
        current_month=ym,
    )
    dashboard_cache.set(cache_key, ctx, ttl=45)

    return render_template('operator/dashboard.html', **ctx)


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
