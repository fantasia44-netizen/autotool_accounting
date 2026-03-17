"""재고 예약/커밋/해제 서비스.

2-Phase 재고 관리:
  1) reserve_stock  — 주문 확정 시 available 차감 (reserved_qty 증가)
  2) commit_stock   — 패킹 완료 시 실재고 차감 (quantity 감소)
  3) release_stock  — 주문 취소 시 예약 해제

재고 3-State:
  - quantity      : 총 재고 (입고 누적)
  - reserved_qty  : 예약 수량
  - available     = quantity - reserved_qty
"""
from datetime import datetime, timezone


def reserve_stock(inv_repo, order_repo, order_id):
    """주문 확정(confirmed) 시 재고 예약.

    FIFO: 유통기한 빠른 재고부터 예약.
    부족 시 전체 롤백 후 에러.

    Returns:
        dict: {ok: True, reservations: [...]} or {ok: False, error: ...}
    """
    order = order_repo.get_order_with_items(order_id)
    if not order or not order.get('items'):
        return {'ok': False, 'error': '주문 정보가 없습니다.'}

    reservations = []  # 성공한 예약 목록 (롤백용)

    for item in order['items']:
        sku_id = item.get('sku_id')
        needed = item.get('quantity', 0)
        if not sku_id or needed <= 0:
            continue

        stocks = inv_repo.list_stock_by_sku(sku_id)
        # FIFO: 유통기한 오름차순
        stocks.sort(key=lambda s: s.get('expiry_date') or '9999-12-31')

        remaining = needed
        for stock in stocks:
            if remaining <= 0:
                break
            qty = stock.get('quantity', 0)
            reserved = stock.get('reserved_qty', 0)
            available = qty - reserved
            if available <= 0:
                continue

            reserve_qty = min(remaining, available)

            # reserved_qty 증가
            ok = inv_repo.update_reserved_qty(
                stock['id'], reserved + reserve_qty)
            if not ok:
                # 롤백
                _rollback_reservations(inv_repo, reservations)
                return {'ok': False, 'error': f'재고 예약 실패 (SKU {sku_id})'}

            # 예약 내역 기록
            res = inv_repo.create_reservation({
                'order_id': order_id,
                'sku_id': sku_id,
                'location_id': stock.get('location_id'),
                'lot_number': stock.get('lot_number'),
                'reserved_qty': reserve_qty,
                'status': 'reserved',
            })
            reservations.append({
                'stock_id': stock['id'],
                'reservation': res,
                'qty': reserve_qty,
                'prev_reserved': reserved,
            })
            remaining -= reserve_qty

        if remaining > 0:
            # 재고 부족 → 전체 롤백
            _rollback_reservations(inv_repo, reservations)
            return {
                'ok': False,
                'error': f'재고 부족: SKU {sku_id} ({remaining}개 부족)',
                'short_sku_id': sku_id,
                'short_qty': remaining,
            }

    return {'ok': True, 'reservations': reservations}


def commit_stock(inv_repo, order_id):
    """패킹 완료 시 실재고 차감 (예약 → 확정).

    reserved_qty 감소 + quantity 감소 + 출고 이력 기록.
    """
    reservations = inv_repo.list_reservations(order_id, status='reserved')
    if not reservations:
        return {'ok': False, 'error': '예약 내역이 없습니다.'}

    now = datetime.now(timezone.utc).isoformat()

    for res in reservations:
        sku_id = res.get('sku_id')
        location_id = res.get('location_id')
        lot_number = res.get('lot_number')
        qty = res.get('reserved_qty', 0)

        # 재고에서 차감
        stock = inv_repo.get_stock(sku_id, location_id, lot_number)
        if stock:
            new_qty = max(0, stock['quantity'] - qty)
            new_reserved = max(0, stock.get('reserved_qty', 0) - qty)
            inv_repo._update(inv_repo.STOCK_TABLE, stock['id'], {
                'quantity': new_qty,
                'reserved_qty': new_reserved,
            })

        # 출고 이력
        inv_repo.log_movement({
            'sku_id': sku_id,
            'location_id': location_id,
            'lot_number': lot_number,
            'movement_type': 'outbound',
            'quantity': -qty,
            'order_id': order_id,
            'memo': f'패킹완료 출고 (주문#{order_id})',
        })

        # reservation → committed
        inv_repo.update_reservation_status(res['id'], 'committed', now)

    return {'ok': True, 'committed_count': len(reservations)}


def release_stock(inv_repo, order_id):
    """주문 취소 시 예약 해제.

    reserved_qty 감소, reservation status → released.
    """
    reservations = inv_repo.list_reservations(order_id, status='reserved')
    if not reservations:
        return {'ok': True, 'released_count': 0}

    for res in reservations:
        sku_id = res.get('sku_id')
        location_id = res.get('location_id')
        lot_number = res.get('lot_number')
        qty = res.get('reserved_qty', 0)

        stock = inv_repo.get_stock(sku_id, location_id, lot_number)
        if stock:
            new_reserved = max(0, stock.get('reserved_qty', 0) - qty)
            inv_repo.update_reserved_qty(stock['id'], new_reserved)

        inv_repo.update_reservation_status(res['id'], 'released')

    return {'ok': True, 'released_count': len(reservations)}


def _rollback_reservations(inv_repo, reservations):
    """예약 실패 시 이미 예약한 것들 되돌리기."""
    for r in reservations:
        try:
            inv_repo.update_reserved_qty(r['stock_id'], r['prev_reserved'])
            if r.get('reservation') and r['reservation'].get('id'):
                inv_repo.update_reservation_status(
                    r['reservation']['id'], 'released')
        except Exception:
            pass  # best-effort 롤백
