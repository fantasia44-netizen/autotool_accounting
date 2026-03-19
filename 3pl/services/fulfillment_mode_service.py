"""
fulfillment_mode_service.py — 듀얼모드 판별 + 강등 로직.

모드: 'speed' (속도모드/A모드) / 'precision' (안정모드/B모드)
강등 원칙: 주문 내 안정모드 SKU가 1개라도 있으면 전체 안정모드로 강제.
"""

SPEED = 'speed'
PRECISION = 'precision'
VALID_MODES = {SPEED, PRECISION}

# 단품/합포 구분
PACK_SINGLE = 'single'
PACK_MULTI = 'multi'


def get_sku_mode(client, sku):
    """SKU의 풀필먼트 모드 결정.

    우선순위: SKU 오버라이드 > 고객사 설정 > 기본값(precision)
    """
    override = (sku.get('fulfillment_mode_override') or '').strip()
    if override in VALID_MODES:
        return override
    client_mode = (client.get('fulfillment_mode') or PRECISION).strip()
    return client_mode if client_mode in VALID_MODES else PRECISION


def determine_order_mode(client, order_items, sku_map):
    """주문의 풀필먼트 모드 결정 (강등 원칙 적용).

    Args:
        client: 고객사 dict (fulfillment_mode 포함)
        order_items: 주문 항목 리스트 [{sku_id, qty, ...}]
        sku_map: {sku_id: sku_dict} 매핑

    Returns:
        dict: {
            'mode': 'speed' | 'precision',
            'pack_type': 'single' | 'multi',
            'downgraded': bool,  # 강등 발생 여부
            'reason': str | None,
        }
    """
    if not order_items:
        return {
            'mode': PRECISION,
            'pack_type': PACK_SINGLE,
            'downgraded': False,
            'reason': None,
        }

    # 각 SKU의 모드 수집
    modes = []
    for item in order_items:
        sku = sku_map.get(item.get('sku_id'))
        if sku:
            modes.append(get_sku_mode(client, sku))
        else:
            modes.append(PRECISION)  # SKU 정보 없으면 안전하게 안정모드

    # 강등 원칙: precision이 하나라도 있으면 전체 precision
    has_precision = PRECISION in modes
    client_mode = (client.get('fulfillment_mode') or PRECISION).strip()

    if client_mode == PRECISION:
        mode = PRECISION
        downgraded = False
        reason = None
    elif has_precision:
        mode = PRECISION
        downgraded = True
        reason = '안정모드 SKU 포함으로 전체 강등'
    else:
        mode = SPEED
        downgraded = False
        reason = None

    # 단품/합포 분류
    total_distinct_skus = len(set(item.get('sku_id') for item in order_items))
    pack_type = PACK_SINGLE if total_distinct_skus == 1 else PACK_MULTI

    return {
        'mode': mode,
        'pack_type': pack_type,
        'downgraded': downgraded,
        'reason': reason,
    }


def classify_orders_by_mode(orders_with_mode):
    """주문 리스트를 모드+단품/합포별로 분류.

    Args:
        orders_with_mode: [{order, mode, pack_type}, ...]

    Returns:
        dict: {
            'speed_single': [orders],   # 속도모드 단품
            'speed_multi': [orders],    # 속도모드 합포
            'precision': [orders],      # 안정모드 (단품/합포 구분 불필요)
        }
    """
    result = {
        'speed_single': [],
        'speed_multi': [],
        'precision': [],
    }

    for item in orders_with_mode:
        mode = item.get('mode', PRECISION)
        pack_type = item.get('pack_type', PACK_SINGLE)

        if mode == SPEED:
            if pack_type == PACK_SINGLE:
                result['speed_single'].append(item)
            else:
                result['speed_multi'].append(item)
        else:
            result['precision'].append(item)

    return result
