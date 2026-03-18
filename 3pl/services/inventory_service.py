"""재고 예약/커밋/해제 서비스.

RPC 기반 원자적 연산 사용 (동시접속 레이스컨디션 방지).

2-Phase 재고 관리:
  1) reserve_stock  — 주문 확정 시 available 차감 (reserved_qty 증가)
  2) commit_stock   — 패킹 완료 시 실재고 차감 (quantity 감소)
  3) release_stock  — 주문 취소 시 예약 해제

재고 3-State:
  - quantity      : 총 재고 (입고 누적)
  - reserved_qty  : 예약 수량
  - available     = quantity - reserved_qty
"""
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _call_rpc(inv_repo, fn_name, params):
    """Supabase RPC 호출 래퍼."""
    try:
        res = inv_repo.client.rpc(fn_name, params).execute()
        if res.data:
            result = res.data
            if isinstance(result, str):
                result = json.loads(result)
            return result
        return {'ok': False, 'error': 'RPC 응답 없음'}
    except Exception as e:
        logger.error('RPC %s 호출 실패: %s', fn_name, str(e))
        raise


def reserve_stock(inv_repo, order_repo, order_id):
    """주문 확정(confirmed) 시 재고 예약 — RPC fn_reserve_stock 사용.

    FIFO: 유통기한 빠른 재고부터 예약.
    부족 시 전체 ROLLBACK (DB 트랜잭션 내부).

    Returns:
        dict: {ok: True, reservations: [...]} or {ok: False, error: ...}
    """
    order = order_repo.get_order_with_items(order_id)
    if not order or not order.get('items'):
        return {'ok': False, 'error': '주문 정보가 없습니다.'}

    items = []
    for item in order['items']:
        sku_id = item.get('sku_id')
        quantity = item.get('quantity', 0)
        if sku_id and quantity > 0:
            items.append({'sku_id': sku_id, 'quantity': quantity})

    if not items:
        return {'ok': False, 'error': '예약할 품목이 없습니다.'}

    result = _call_rpc(inv_repo, 'fn_reserve_stock', {
        'p_operator_id': inv_repo.operator_id,
        'p_order_id': order_id,
        'p_items': json.dumps(items),
    })

    return result


def commit_stock(inv_repo, order_id):
    """패킹 완료 시 실재고 차감 — RPC fn_commit_stock 사용.

    멱등성 보장: 이미 committed 된 주문이면 {ok: True, message: '이미 처리됨'} 반환.
    """
    result = _call_rpc(inv_repo, 'fn_commit_stock', {
        'p_operator_id': inv_repo.operator_id,
        'p_order_id': order_id,
    })

    return result


def release_stock(inv_repo, order_id):
    """주문 취소 시 예약 해제.

    NOTE: release는 빈도가 낮고 경합이 적으므로 기존 Python 로직 유지.
    향후 필요 시 RPC로 전환 가능.
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
