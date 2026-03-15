"""고객사 포털 — 재고조회, 주문현황, 출고영상, 과금조회."""
from flask import Blueprint, render_template, request, Response
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


# ═══ 과금 조회 ═══

@client_bp.route('/billing')
@login_required
@_require_client
def billing():
    from db_utils import get_repo
    from datetime import datetime, timezone
    billing_repo = get_repo('client_billing')
    cid = current_user.client_id

    ym = request.args.get('month') or datetime.now(timezone.utc).strftime('%Y-%m')
    summary = billing_repo.get_monthly_summary(cid, ym)
    invoices = billing_repo.list_invoices(client_id=cid, limit=12)

    from services.client_billing_service import CATEGORY_LABELS
    return render_template('client/billing.html',
                           summary=summary,
                           invoices=invoices,
                           category_labels=CATEGORY_LABELS,
                           current_month=ym)


@client_bp.route('/billing/export')
@login_required
@_require_client
def billing_export():
    """과금 내역 엑셀 다운로드."""
    from db_utils import get_repo
    from datetime import datetime, timezone
    billing_repo = get_repo('client_billing')
    cid = current_user.client_id

    ym = request.args.get('month') or datetime.now(timezone.utc).strftime('%Y-%m')
    summary = billing_repo.get_monthly_summary(cid, ym)
    items = summary.get('items', [])

    return _export_billing_excel(items, ym)


@client_bp.route('/inventory/export')
@login_required
@_require_client
def inventory_export():
    """재고 현황 엑셀 다운로드."""
    from db_utils import get_repo
    inv_repo = get_repo('inventory')
    skus = inv_repo.list_skus(client_id=current_user.client_id) or []
    stocks = inv_repo.list_all_stock() or []

    # SKU별 재고 합산
    sku_stock = {}
    for st in stocks:
        sid = st.get('sku_id')
        sku_stock[sid] = sku_stock.get(sid, 0) + st.get('quantity', 0)

    return _export_inventory_excel(skus, sku_stock)


def _export_billing_excel(items, year_month):
    """과금 내역 → 엑셀 응답."""
    import io
    try:
        from openpyxl import Workbook
    except ImportError:
        return Response('openpyxl 미설치', status=500)

    wb = Workbook()
    ws = wb.active
    ws.title = '과금내역'
    ws.append(['일시', '카테고리', '항목명', '수량', '단가', '금액', '메모'])
    for r in items:
        ws.append([
            r.get('created_at', '')[:16] if r.get('created_at') else '',
            r.get('category', ''),
            r.get('fee_name', ''),
            r.get('quantity', 0),
            r.get('unit_price', 0),
            r.get('total_amount', 0),
            r.get('memo', ''),
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f'billing_{year_month}.xlsx'
    return Response(
        buf.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={fname}'},
    )


def _export_inventory_excel(skus, sku_stock):
    """재고 현황 → 엑셀 응답."""
    import io
    try:
        from openpyxl import Workbook
    except ImportError:
        return Response('openpyxl 미설치', status=500)

    wb = Workbook()
    ws = wb.active
    ws.title = '재고현황'
    ws.append(['SKU코드', '바코드', '품명', '카테고리', '보관온도', '현재고', '최소재고'])
    for s in skus:
        ws.append([
            s.get('sku_code', ''),
            s.get('barcode', ''),
            s.get('name', ''),
            s.get('category', ''),
            s.get('storage_temp', 'ambient'),
            sku_stock.get(s['id'], 0),
            s.get('min_stock_qty', 0),
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=inventory.xlsx'},
    )
