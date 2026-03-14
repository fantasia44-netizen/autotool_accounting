"""주문/출고/피킹/패킹 관련 라우트."""
import logging
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from . import operator_bp, _require_operator

logger = logging.getLogger(__name__)


# ═══ 주문관리 ═══

@operator_bp.route('/orders')
@login_required
@_require_operator
def orders():
    from db_utils import get_repo
    repo = get_repo('order')
    status = request.args.get('status')
    channel = request.args.get('channel')
    client_id = request.args.get('client_id', type=int)

    orders_list = repo.list_orders(status=status, channel=channel,
                                   client_id=client_id) or []
    counts = repo.count_by_status() or {}

    client_repo = get_repo('client')
    clients = client_repo.list_clients() or []
    client_map = {c['id']: c['name'] for c in clients}

    return render_template('operator/orders.html', orders=orders_list, counts=counts,
                           filter_status=status, filter_channel=channel,
                           filter_client_id=client_id,
                           clients=clients, client_map=client_map)


@operator_bp.route('/orders/<int:order_id>')
@login_required
@_require_operator
def order_detail(order_id):
    from db_utils import get_repo
    repo = get_repo('order')
    order = repo.get_order_with_items(order_id)
    if not order:
        flash('주문을 찾을 수 없습니다.', 'warning')
        return redirect(url_for('operator.orders'))

    status_logs = repo.get_status_logs(order_id) or []
    shipments = repo.list_shipments(order_id=order_id) or []
    return render_template('operator/order_detail.html', order=order,
                           status_logs=status_logs, shipments=shipments)


@operator_bp.route('/orders/<int:order_id>/status', methods=['POST'])
@login_required
@_require_operator
def order_status_update(order_id):
    from db_utils import get_repo
    repo = get_repo('order')
    order = repo.get_order(order_id)
    old_status = order.get('status', '') if order else ''
    new_status = request.form.get('status')
    reason = request.form.get('reason', '').strip()
    # 재고 예약/해제 연동
    inv_repo = get_repo('inventory')
    if new_status == 'confirmed' and old_status in ('pending', ''):
        from services.inventory_service import reserve_stock
        result = reserve_stock(inv_repo, repo, order_id)
        if not result.get('ok'):
            flash(f'재고 예약 실패: {result.get("error", "알 수 없는 오류")}', 'danger')
            return redirect(url_for('operator.order_detail', order_id=order_id))

    if new_status == 'cancelled' and old_status not in ('cancelled', ''):
        from services.inventory_service import release_stock
        release_stock(inv_repo, order_id)

    repo.update_order_status(order_id, new_status)
    repo.log_status_change(order_id, old_status, new_status,
                           changed_by=current_user.id, reason=reason)
    # 출고 시 과금 기록
    if new_status == 'shipped' and order:
        try:
            cid = order.get('client_id')
            if cid:
                from services.client_billing_service import record_outbound_fee
                record_outbound_fee(get_repo('client_billing'),
                                    get_repo('client_rate'), cid,
                                    order_id=order_id)
        except Exception:
            logger.exception('과금 기록 실패 (출고): order_id=%s, client_id=%s',
                             order_id, order.get('client_id'))
    flash(f'주문 상태가 "{new_status}"로 변경되었습니다.', 'success')
    return redirect(url_for('operator.order_detail', order_id=order_id))


@operator_bp.route('/orders/<int:order_id>/hold', methods=['POST'])
@login_required
@_require_operator
def order_hold(order_id):
    """주문 보류 처리."""
    from db_utils import get_repo
    repo = get_repo('order')
    reason = request.form.get('reason', '').strip() or '관리자 보류'
    order = repo.get_order(order_id)
    if order:
        repo.hold_order(order_id, reason, current_user.id)
        repo.log_status_change(order_id, order.get('status', ''), 'hold',
                               changed_by=current_user.id, reason=reason)
        # 보류 시 예약 해제
        if order.get('status') in ('confirmed', 'picking_ready', 'picking'):
            try:
                inv_repo = get_repo('inventory')
                from services.inventory_service import release_stock
                release_stock(inv_repo, order_id)
            except Exception:
                logger.exception('재고 예약 해제 실패: order_id=%s', order_id)
    flash(f'주문이 보류되었습니다: {reason}', 'warning')
    return redirect(url_for('operator.order_detail', order_id=order_id))


@operator_bp.route('/orders/<int:order_id>/release-hold', methods=['POST'])
@login_required
@_require_operator
def order_release_hold(order_id):
    from db_utils import get_repo
    repo = get_repo('order')
    order = repo.get_order(order_id)
    if order:
        repo.release_hold(order_id)
        repo.log_status_change(order_id, 'hold', order.get('status', ''),
                               changed_by=current_user.id, reason='보류 해제')
    flash('보류가 해제되었습니다.', 'success')
    return redirect(url_for('operator.order_detail', order_id=order_id))


# ═══ 피킹관리 ═══

@operator_bp.route('/picking')
@login_required
@_require_operator
def picking():
    """피킹리스트 관리."""
    from db_utils import get_repo
    picking_repo = get_repo('picking')
    order_repo = get_repo('order')
    client_repo = get_repo('client')
    wh_repo = get_repo('warehouse')

    status = request.args.get('status')
    lists = picking_repo.list_picking_lists(status=status) or []
    counts = picking_repo.count_by_status() or {}

    confirmed_orders = order_repo.list_orders(status='confirmed', limit=100) or []
    clients = client_repo.list_clients() or []
    warehouses = wh_repo.list_warehouses() or []

    return render_template('operator/picking.html', lists=lists, counts=counts,
                           confirmed_orders=confirmed_orders,
                           clients=clients, warehouses=warehouses,
                           filter_status=status)


@operator_bp.route('/picking/generate', methods=['POST'])
@login_required
@_require_operator
def picking_generate():
    """피킹리스트 생성."""
    from db_utils import get_repo
    order_ids_raw = request.form.getlist('order_ids')
    order_ids = [int(x) for x in order_ids_raw if x.isdigit()]
    list_type = request.form.get('list_type', 'by_order')
    warehouse_id = request.form.get('warehouse_id', type=int)
    client_id = request.form.get('client_id', type=int)

    if not order_ids:
        flash('주문을 선택해주세요.', 'warning')
        return redirect(url_for('operator.picking'))

    from services.picking_service import generate_picking_list
    try:
        pl = generate_picking_list(
            picking_repo=get_repo('picking'),
            order_repo=get_repo('order'),
            inv_repo=get_repo('inventory'),
            wh_repo=get_repo('warehouse'),
            order_ids=order_ids,
            warehouse_id=warehouse_id,
            client_id=client_id,
            list_type=list_type,
            created_by=current_user.id,
        )
        flash(f'피킹리스트 {pl.get("list_no", "")} 생성 완료 ({len(pl.get("items", []))}건)', 'success')
    except Exception as e:
        flash(f'피킹리스트 생성 오류: {e}', 'danger')

    return redirect(url_for('operator.picking'))


@operator_bp.route('/picking/<int:list_id>')
@login_required
@_require_operator
def picking_detail(list_id):
    """피킹리스트 상세."""
    from db_utils import get_repo
    repo = get_repo('picking')
    pl = repo.get_picking_list_with_items(list_id)
    if not pl:
        flash('피킹리스트를 찾을 수 없습니다.', 'warning')
        return redirect(url_for('operator.picking'))

    inv_repo = get_repo('inventory')
    sku_map = {}
    for item in pl.get('items', []):
        sid = item.get('sku_id')
        if sid and sid not in sku_map:
            sku = inv_repo.get_sku(sid)
            sku_map[sid] = sku.get('name', f'SKU#{sid}') if sku else f'SKU#{sid}'

    return render_template('operator/picking_detail.html', pl=pl, sku_map=sku_map)


@operator_bp.route('/picking/<int:list_id>/complete', methods=['POST'])
@login_required
@_require_operator
def picking_complete(list_id):
    """피킹리스트 완료."""
    from db_utils import get_repo
    repo = get_repo('picking')
    repo.complete_picking_list(list_id)
    flash('피킹리스트가 완료 처리되었습니다.', 'success')
    return redirect(url_for('operator.picking_detail', list_id=list_id))


# ═══ 출고관리 ═══

@operator_bp.route('/shipments')
@login_required
@_require_operator
def shipments():
    from db_utils import get_repo
    repo = get_repo('order')
    status = request.args.get('status')
    shipment_type = request.args.get('type', 'normal')
    items = repo.list_shipments(status=status, shipment_type=shipment_type)
    counts = repo.count_shipments_by_status()
    client_repo = get_repo('client')
    clients = client_repo.list_clients() or []
    client_map = {c['id']: c['name'] for c in clients}
    wh_repo = get_repo('warehouse')
    warehouses = wh_repo.list_warehouses() or []
    inv_repo = get_repo('inventory')
    skus = inv_repo.list_skus() or []
    return render_template('operator/shipments.html', shipments=items, counts=counts,
                           filter_status=status, filter_type=shipment_type,
                           clients=clients, client_map=client_map,
                           warehouses=warehouses, skus=skus)


@operator_bp.route('/shipments/return', methods=['POST'])
@login_required
@_require_operator
def shipment_return_create():
    """반품출고 생성."""
    from db_utils import get_repo
    repo = get_repo('order')
    client_id = request.form.get('client_id', type=int)
    sku_id = request.form.get('sku_id', type=int)
    quantity = request.form.get('quantity', type=int)
    reason = request.form.get('reason', '').strip()

    if not all([client_id, sku_id, quantity]):
        flash('필수 항목을 입력해주세요.', 'warning')
        return redirect(url_for('operator.shipments', type='return'))

    repo.create_shipment({
        'shipment_type': 'return',
        'client_id': client_id,
        'sku_id': sku_id,
        'quantity': quantity,
        'reason': reason,
        'status': 'pending',
    })
    # 반품비 과금
    try:
        from services.client_billing_service import record_return_fee
        record_return_fee(get_repo('client_billing'),
                          get_repo('client_rate'), client_id, memo=reason)
    except Exception:
        logger.exception('과금 기록 실패 (반품): client_id=%s', client_id)
    flash(f'반품출고 등록 완료 ({quantity}개)', 'success')
    return redirect(url_for('operator.shipments', type='return'))


@operator_bp.route('/shipments/transfer', methods=['POST'])
@login_required
@_require_operator
def shipment_transfer_create():
    """창고이동 생성."""
    from db_utils import get_repo
    repo = get_repo('order')
    inv_repo = get_repo('inventory')
    sku_id = request.form.get('sku_id', type=int)
    quantity = request.form.get('quantity', type=int)
    from_wh = request.form.get('from_warehouse_id', type=int)
    to_wh = request.form.get('to_warehouse_id', type=int)
    reason = request.form.get('reason', '').strip()

    if not all([sku_id, quantity, from_wh, to_wh]):
        flash('필수 항목을 입력해주세요.', 'warning')
        return redirect(url_for('operator.shipments', type='transfer'))

    if from_wh == to_wh:
        flash('출발 창고와 도착 창고가 같습니다.', 'warning')
        return redirect(url_for('operator.shipments', type='transfer'))

    repo.create_shipment({
        'shipment_type': 'transfer',
        'sku_id': sku_id,
        'quantity': quantity,
        'from_warehouse_id': from_wh,
        'to_warehouse_id': to_wh,
        'reason': reason or '창고이동',
        'status': 'pending',
    })

    inv_repo.log_movement({
        'sku_id': sku_id,
        'movement_type': 'transfer_out',
        'quantity': -quantity,
        'memo': '창고이동 (출발)',
        'user_id': current_user.id,
    })
    inv_repo.log_movement({
        'sku_id': sku_id,
        'movement_type': 'transfer_in',
        'quantity': quantity,
        'memo': '창고이동 (도착)',
        'user_id': current_user.id,
    })

    flash(f'창고이동 등록 완료 ({quantity}개)', 'success')
    return redirect(url_for('operator.shipments', type='transfer'))


# ═══ 패킹센터 (운영사 뷰) ═══

@operator_bp.route('/packing')
@login_required
@_require_operator
def packing():
    from db_utils import get_repo
    repo = get_repo('packing')
    jobs = repo.list_jobs()
    return render_template('operator/packing.html', jobs=jobs)
