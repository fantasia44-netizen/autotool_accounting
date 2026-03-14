"""상품 스캔 검증 서비스.

패킹 시 상품 바코드를 스캔할 때,
주문에 포함된 SKU/수량과 실제 스캔한 상품을 대조하여
오출고를 사전 차단한다.
"""


def validate_scanned_item(inv_repo, order_items, scanned_barcode, already_scanned):
    """상품 바코드 스캔 검증.

    Args:
        inv_repo: InventoryRepository 인스턴스
        order_items: 주문 아이템 목록 [{sku_id, quantity, ...}, ...]
        scanned_barcode: 스캔한 바코드 문자열
        already_scanned: 이미 스캔된 SKU별 수량 {sku_id: count, ...}

    Returns:
        dict: {
            'valid': bool,
            'error': str (오류 메시지, valid=False일 때),
            'error_type': str (오류 유형 코드),
            'sku': dict (SKU 정보, valid=True일 때),
            'sku_id': int,
            'remaining': int (남은 스캔 수량),
            'expected_qty': int,
            'scanned_qty': int (이번 포함 누적),
        }
    """
    if not scanned_barcode:
        return _error('empty', '바코드를 입력해주세요.')

    # 1. 바코드로 SKU 조회
    sku = inv_repo.get_sku_by_barcode(scanned_barcode)
    if not sku:
        # sku_code로도 시도
        sku = inv_repo.get_sku_by_code(scanned_barcode)

    if not sku:
        return _error('not_found', f'등록되지 않은 바코드입니다: {scanned_barcode}')

    sku_id = sku['id']

    # 2. 주문에 포함된 SKU인지 확인
    expected_item = None
    for item in order_items:
        if item.get('sku_id') == sku_id:
            expected_item = item
            break

    if not expected_item:
        return _error(
            'wrong_product',
            f'주문에 없는 상품입니다: {sku.get("name", scanned_barcode)}',
            sku=sku,
        )

    # 3. 수량 확인
    expected_qty = expected_item.get('quantity', 1)
    current_scanned = already_scanned.get(str(sku_id), 0)
    new_scanned = current_scanned + 1

    if new_scanned > expected_qty:
        return _error(
            'over_quantity',
            f'수량 초과: {sku.get("name", "")} '
            f'(필요 {expected_qty}개, 이미 {current_scanned}개 스캔)',
            sku=sku,
        )

    remaining = expected_qty - new_scanned

    return {
        'valid': True,
        'sku': sku,
        'sku_id': sku_id,
        'expected_qty': expected_qty,
        'scanned_qty': new_scanned,
        'remaining': remaining,
    }


def get_scan_summary(order_items, already_scanned):
    """전체 스캔 진행률 요약.

    Returns:
        dict: {
            'total_expected': int,
            'total_scanned': int,
            'all_complete': bool,
            'items': [{sku_id, expected, scanned, complete}, ...],
        }
    """
    total_expected = 0
    total_scanned = 0
    items = []

    for item in order_items:
        sku_id = item.get('sku_id')
        expected = item.get('quantity', 1)
        scanned = already_scanned.get(str(sku_id), 0)
        total_expected += expected
        total_scanned += scanned
        items.append({
            'sku_id': sku_id,
            'expected': expected,
            'scanned': scanned,
            'complete': scanned >= expected,
        })

    return {
        'total_expected': total_expected,
        'total_scanned': total_scanned,
        'all_complete': total_scanned >= total_expected,
        'items': items,
    }


def _error(error_type, message, sku=None):
    result = {
        'valid': False,
        'error': message,
        'error_type': error_type,
    }
    if sku:
        result['sku'] = sku
    return result
