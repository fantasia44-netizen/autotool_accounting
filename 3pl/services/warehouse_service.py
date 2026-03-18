"""창고 관리 서비스 — 입고/출고 프로세스.

RPC 기반 원자적 재고 연산 사용 (동시접속 레이스컨디션 방지).
"""
import json
import logging
from db_utils import get_repo

logger = logging.getLogger(__name__)


def _call_rpc(inv_repo, fn_name, params):
    """Supabase RPC 호출 래퍼. 결과를 dict로 반환."""
    try:
        res = inv_repo.client.rpc(fn_name, params).execute()
        if res.data:
            result = res.data
            if isinstance(result, str):
                result = json.loads(result)
            return result
        return {'ok': False, 'error': 'RPC 응답 없음'}
    except Exception as e:
        err_msg = str(e)
        logger.error('RPC %s 호출 실패: %s', fn_name, err_msg)
        # 재고 부족 등 비즈니스 에러 추출
        if '재고 부족' in err_msg or '출발지 재고 부족' in err_msg:
            raise ValueError(err_msg)
        raise


def process_inbound(inv_repo, sku_id, location_id, quantity,
                    lot_number=None, memo='', user_id=None):
    """입고 처리: RPC fn_adjust_stock으로 원자적 재고 증가 + 이력 기록."""
    result = _call_rpc(inv_repo, 'fn_adjust_stock', {
        'p_operator_id': inv_repo.operator_id,
        'p_sku_id': sku_id,
        'p_location_id': location_id,
        'p_delta': quantity,
        'p_lot_number': lot_number,
        'p_memo': memo or '입고',
        'p_user_id': user_id,
    })

    if not result.get('ok'):
        raise ValueError(result.get('error', '입고 처리 실패'))

    return result


def process_outbound(order_id, items, user_id=None):
    """출고 처리: 각 아이템별 RPC fn_adjust_stock으로 원자적 차감."""
    inv_repo = get_repo('inventory')
    order_repo = get_repo('order')

    for item in items:
        result = _call_rpc(inv_repo, 'fn_adjust_stock', {
            'p_operator_id': inv_repo.operator_id,
            'p_sku_id': item['sku_id'],
            'p_location_id': item['location_id'],
            'p_delta': -item['quantity'],
            'p_lot_number': item.get('lot_number'),
            'p_memo': f'출고 (주문#{order_id})',
            'p_user_id': user_id,
        })

        if not result.get('ok'):
            raise ValueError(result.get('error', f"재고 부족: SKU {item['sku_id']}"))

    order_repo.update_order_status(order_id, 'shipped')


def process_transfer(inv_repo, sku_id, from_location_id, to_location_id,
                     quantity, lot_number=None, memo='', user_id=None):
    """창고 이동: RPC fn_transfer_stock으로 원자적 이동 (출발 차감 + 도착 증가)."""
    result = _call_rpc(inv_repo, 'fn_transfer_stock', {
        'p_operator_id': inv_repo.operator_id,
        'p_sku_id': sku_id,
        'p_from_location_id': from_location_id,
        'p_to_location_id': to_location_id,
        'p_quantity': quantity,
        'p_lot_number': lot_number,
        'p_memo': memo or '창고이동',
        'p_user_id': user_id,
    })

    if not result.get('ok'):
        raise ValueError(result.get('error', '창고 이동 실패'))

    return result
