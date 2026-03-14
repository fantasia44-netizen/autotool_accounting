"""출고 차단 검증 서비스.

스캔 시점에 주문의 최종 상태를 재검증하여
취소/보류/출고완료 등 문제 주문의 출고를 사전 차단한다.
"""

# 출고가 허용되는 주문 상태
SHIPPABLE_STATUSES = {
    'confirmed', 'picking_ready', 'picking', 'picked',
    'packing', 'packed',
}

# 차단 사유 메시지
BLOCK_REASONS = {
    'cancelled': '취소된 주문입니다.',
    'hold': '보류 처리된 주문입니다.',
    'shipped': '이미 출고 완료된 주문입니다.',
    'delivered': '이미 배송 완료된 주문입니다.',
    'pending': '아직 확정되지 않은 주문입니다.',
    'duplicate_invoice': '이미 송장이 등록된 주문입니다.',
    'unknown': '출고할 수 없는 상태입니다.',
}


def validate_order_for_shipping(order_repo, order_id):
    """스캔 시점 주문 최종 검증.

    Returns:
        dict: {
            'blocked': bool,
            'reason': str (차단 사유, blocked=True일 때),
            'block_type': str (차단 유형 코드),
            'order': dict (주문 데이터, blocked=False일 때),
        }
    """
    # 1. 주문 최신 상태 재조회
    order = order_repo.get_order(order_id)
    if not order:
        return {
            'blocked': True,
            'reason': '주문을 찾을 수 없습니다.',
            'block_type': 'not_found',
        }

    status = order.get('status', '')

    # 2. 취소 확인
    if status == 'cancelled':
        return _blocked('cancelled')

    # 3. 보류 플래그 확인
    if order.get('hold_flag'):
        reason = order.get('hold_reason') or BLOCK_REASONS['hold']
        return {
            'blocked': True,
            'reason': f"보류: {reason}",
            'block_type': 'hold',
        }

    # 4. 이미 출고/배송 완료
    if status == 'shipped':
        return _blocked('shipped')
    if status == 'delivered':
        return _blocked('delivered')

    # 5. 미확정 주문
    if status == 'pending':
        return _blocked('pending')

    # 6. 허용 상태 체크
    if status not in SHIPPABLE_STATUSES:
        return {
            'blocked': True,
            'reason': f"현재 상태({status})에서는 출고할 수 없습니다.",
            'block_type': 'invalid_status',
        }

    # 7. 송장 중복 확인 (이미 shipped 상태인 shipment가 있는지)
    shipments = order_repo.list_shipments(order_id=order_id, status='shipped')
    if shipments:
        return _blocked('duplicate_invoice')

    # 통과
    return {
        'blocked': False,
        'order': order,
    }


def _blocked(block_type):
    return {
        'blocked': True,
        'reason': BLOCK_REASONS.get(block_type, BLOCK_REASONS['unknown']),
        'block_type': block_type,
    }
