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
    # 출고 시 과금 기록 (서비스 내부에서 DLQ 처리)
    if new_status == 'shipped' and order:
        try:
            cid = order.get('client_id')
            if cid:
                from services.client_billing_service import record_outbound_fee
                # 주문 아이템 수 / 총 중량 계산 → 조건부 과금
                order_full = repo.get_order_with_items(order_id)
                items = order_full.get('items', []) if order_full else []
                item_count = len(items)
                total_weight_g = sum(
                    (it.get('weight_g', 0) or 0) * abs(it.get('quantity', it.get('qty', 1)))
                    for it in items
                )
                record_outbound_fee(get_repo('client_billing'),
                                    get_repo('client_rate'), cid,
                                    order_id=order_id,
                                    item_count=item_count,
                                    total_weight_g=total_weight_g)
        except Exception:
            logger.exception('과금 서비스 호출 자체 실패 (출고): order_id=%s', order_id)
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


# ═══ 택배출고 ═══

@operator_bp.route('/shipments')
@login_required
@_require_operator
def shipments():
    """택배출고 목록."""
    from db_utils import get_repo
    repo = get_repo('order')
    status = request.args.get('status')
    items = repo.list_shipments(status=status, shipment_type='normal')
    counts = repo.count_shipments_by_status()
    client_repo = get_repo('client')
    clients = client_repo.list_clients() or []
    client_map = {c['id']: c['name'] for c in clients}

    # order_id → client_id 매핑 (1회 bulk 조회)
    order_ids = list({s['order_id'] for s in items if s.get('order_id')})
    if order_ids:
        order_rows = repo._query(repo.ORDER_TABLE,
                                  columns='id,client_id,order_no',
                                  filters=[('id', 'in', order_ids)],
                                  limit=len(order_ids))
        order_client = {o['id']: o.get('client_id') for o in order_rows}
        for s in items:
            if s.get('order_id') and not s.get('client_id'):
                s['client_id'] = order_client.get(s['order_id'])

    return render_template('operator/shipments.html', shipments=items, counts=counts,
                           filter_status=status, client_map=client_map)


# ═══ 반품관리 (고객 회송) ═══

@operator_bp.route('/returns')
@login_required
@_require_operator
def returns():
    """반품관리 목록."""
    from db_utils import get_repo
    repo = get_repo('order')
    status = request.args.get('status')
    items = repo.list_shipments(status=status, shipment_type='return')
    client_repo = get_repo('client')
    clients = client_repo.list_clients() or []
    client_map = {c['id']: c['name'] for c in clients}
    wh_repo = get_repo('warehouse')
    warehouses = wh_repo.list_warehouses() or []
    locations = wh_repo.list_all_locations_with_path()
    inv_repo = get_repo('inventory')
    skus = inv_repo.list_skus() or []
    sku_map = {s['id']: f"{s['sku_code']} — {s['name']}" for s in skus}
    return render_template('operator/returns.html', shipments=items,
                           clients=clients, client_map=client_map,
                           warehouses=warehouses, locations=locations,
                           skus=skus, sku_map=sku_map, filter_status=status)


@operator_bp.route('/returns/create', methods=['POST'])
@login_required
@_require_operator
def return_create():
    """반품 등록 (고객 회송)."""
    from db_utils import get_repo
    repo = get_repo('order')
    inv_repo = get_repo('inventory')
    client_id = request.form.get('client_id', type=int)
    sku_id = request.form.get('sku_id', type=int)
    quantity = request.form.get('quantity', type=int)
    reason = request.form.get('reason', '').strip()
    location_id = request.form.get('location_id', type=int)

    if not all([client_id, sku_id, quantity]):
        flash('필수 항목을 입력해주세요.', 'warning')
        return redirect(url_for('operator.returns'))

    repo.create_shipment({
        'shipment_type': 'return',
        'client_id': client_id,
        'sku_id': sku_id,
        'quantity': quantity,
        'reason': reason,
        'location_id': location_id,
        'status': 'pending',
    })

    # 재고 복원: movement 기록 + stock 수량 증가
    inv_repo.log_movement({
        'sku_id': sku_id,
        'location_id': location_id,
        'movement_type': 'return_in',
        'quantity': quantity,
        'memo': f'반품입고: {reason}' if reason else '반품입고',
        'user_id': current_user.id,
    })
    if location_id:
        try:
            inv_repo.adjust_stock(sku_id, location_id, delta=quantity)
        except Exception:
            logger.exception('반품 재고 수량 반영 실패: sku_id=%s, location_id=%s', sku_id, location_id)

    # 반품비 과금
    try:
        from services.client_billing_service import record_return_fee
        record_return_fee(get_repo('client_billing'),
                          get_repo('client_rate'), client_id,
                          quantity=quantity, memo=reason)
    except Exception:
        logger.exception('과금 서비스 호출 자체 실패 (반품): client_id=%s', client_id)
    flash(f'반품 등록 완료 ({quantity}개)', 'success')
    return redirect(url_for('operator.returns'))


# ═══ 창고이동 ═══

@operator_bp.route('/transfers')
@login_required
@_require_operator
def transfers():
    """창고이동 목록."""
    from db_utils import get_repo
    repo = get_repo('order')
    status = request.args.get('status')
    items = repo.list_shipments(status=status, shipment_type='transfer')
    wh_repo = get_repo('warehouse')
    warehouses = wh_repo.list_warehouses() or []
    locations = wh_repo.list_all_locations_with_path()
    inv_repo = get_repo('inventory')
    skus = inv_repo.list_skus() or []
    sku_map = {s['id']: f"{s['sku_code']} — {s['name']}" for s in skus}
    wh_map = {w['id']: w['name'] for w in warehouses}
    return render_template('operator/transfers.html', shipments=items,
                           warehouses=warehouses, locations=locations,
                           skus=skus, sku_map=sku_map, wh_map=wh_map,
                           filter_status=status)


@operator_bp.route('/transfers/create', methods=['POST'])
@login_required
@_require_operator
def transfer_create():
    """창고이동 생성."""
    from db_utils import get_repo
    repo = get_repo('order')
    inv_repo = get_repo('inventory')
    sku_id = request.form.get('sku_id', type=int)
    quantity = request.form.get('quantity', type=int)
    from_loc = request.form.get('from_location_id', type=int)
    to_loc = request.form.get('to_location_id', type=int)
    reason = request.form.get('reason', '').strip()

    if not all([sku_id, quantity]):
        flash('필수 항목을 입력해주세요.', 'warning')
        return redirect(url_for('operator.transfers'))

    if from_loc and to_loc and from_loc == to_loc:
        flash('출발 로케이션과 도착 로케이션이 같습니다.', 'warning')
        return redirect(url_for('operator.transfers'))

    repo.create_shipment({
        'shipment_type': 'transfer',
        'sku_id': sku_id,
        'quantity': quantity,
        'from_warehouse_id': from_loc,
        'to_warehouse_id': to_loc,
        'reason': reason or '창고이동',
        'status': 'completed',
    })

    # 출발 로케이션 재고 차감
    if from_loc:
        inv_repo.log_movement({
            'sku_id': sku_id,
            'location_id': from_loc,
            'movement_type': 'transfer_out',
            'quantity': -quantity,
            'memo': f'이동출고: {reason}' if reason else '이동출고',
            'user_id': current_user.id,
        })
        try:
            inv_repo.adjust_stock(sku_id, from_loc, delta=-quantity)
        except Exception:
            logger.exception('이동 출고 재고 반영 실패')

    # 도착 로케이션 재고 증가
    if to_loc:
        inv_repo.log_movement({
            'sku_id': sku_id,
            'location_id': to_loc,
            'movement_type': 'transfer_in',
            'quantity': quantity,
            'memo': f'이동입고: {reason}' if reason else '이동입고',
            'user_id': current_user.id,
        })
        try:
            inv_repo.adjust_stock(sku_id, to_loc, delta=quantity)
        except Exception:
            logger.exception('이동 입고 재고 반영 실패')

    flash(f'창고이동 완료 ({quantity}개)', 'success')
    return redirect(url_for('operator.transfers'))


# ═══ 패킹센터 (운영사 뷰) ═══

@operator_bp.route('/packing')
@login_required
@_require_operator
def packing():
    from db_utils import get_repo
    repo = get_repo('packing')
    jobs = repo.list_jobs()
    return render_template('operator/packing.html', jobs=jobs)
