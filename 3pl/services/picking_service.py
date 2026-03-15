"""피킹리스트 생성 서비스.

주문 목록 → 재고 위치 매칭 → 피킹리스트 자동 생성.
FIFO (유통기한 빠른 것 우선) 자동 배정.
"""
from datetime import datetime, timezone


def generate_picking_list(picking_repo, order_repo, inv_repo, wh_repo,
                          order_ids, warehouse_id=None, client_id=None,
                          list_type='by_order', created_by=None):
    """피킹리스트 생성.

    Args:
        order_ids: 피킹할 주문 ID 목록
        warehouse_id: 대상 창고 (선택)
        client_id: 대상 화주사 (선택)
        list_type: 'by_order' | 'by_product' | 'by_location'
        created_by: 생성자 user_id

    Returns:
        dict: 생성된 picking_list (items 포함)
    """
    if not order_ids:
        raise ValueError('주문을 선택해주세요.')

    # 1. 주문별 필요 SKU/수량 수집
    sku_demand = {}  # {sku_id: {'total_qty': N, 'order_ids': [...]}}
    for oid in order_ids:
        order = order_repo.get_order_with_items(oid)
        if not order or not order.get('items'):
            continue
        for item in order['items']:
            sid = item.get('sku_id')
            qty = item.get('quantity', 0)
            if sid not in sku_demand:
                sku_demand[sid] = {'total_qty': 0, 'orders': {}}
            sku_demand[sid]['total_qty'] += qty
            sku_demand[sid]['orders'][oid] = \
                sku_demand[sid]['orders'].get(oid, 0) + qty

    if not sku_demand:
        raise ValueError('피킹할 상품이 없습니다.')

    # 2. 각 SKU에 대해 재고 위치 매칭 (FIFO by expiry_date)
    picking_items = []
    for sku_id, demand in sku_demand.items():
        needed = demand['total_qty']
        stocks = inv_repo.list_stock_by_sku(sku_id)

        # 유통기한 만료 재고 제외 + 오름차순 정렬 (FIFO)
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        stocks = [s for s in stocks
                  if not s.get('expiry_date') or s['expiry_date'] >= today]
        stocks.sort(key=lambda s: s.get('expiry_date') or '9999-12-31')

        remaining = needed
        for stock in stocks:
            if remaining <= 0:
                break
            available = stock.get('quantity', 0) - stock.get('reserved_qty', 0)
            if available <= 0:
                continue

            pick_qty = min(remaining, available)
            location_id = stock.get('location_id')

            # 로케이션 코드 조회
            location_code = ''
            if location_id:
                try:
                    locs = wh_repo.list_all_locations()
                    for loc in locs:
                        if loc.get('id') == location_id:
                            location_code = loc.get('code', '')
                            break
                except Exception:
                    pass

            # 주문별 vs 합산 분리
            if list_type == 'by_order':
                for oid, oqty in demand['orders'].items():
                    if remaining <= 0:
                        break
                    item_qty = min(oqty, pick_qty, remaining)
                    picking_items.append({
                        'order_id': oid,
                        'sku_id': sku_id,
                        'location_id': location_id,
                        'location_code': location_code,
                        'expected_qty': item_qty,
                        'lot_number': stock.get('lot_number'),
                    })
                    remaining -= item_qty
                    pick_qty -= item_qty
            else:
                picking_items.append({
                    'order_id': None,
                    'sku_id': sku_id,
                    'location_id': location_id,
                    'location_code': location_code,
                    'expected_qty': pick_qty,
                    'lot_number': stock.get('lot_number'),
                })
                remaining -= pick_qty

        # 재고 부족 시 short 항목
        if remaining > 0:
            picking_items.append({
                'order_id': None,
                'sku_id': sku_id,
                'location_id': None,
                'location_code': '재고부족',
                'expected_qty': remaining,
                'lot_number': None,
                'status': 'short',
            })

    # 3. 정렬
    if list_type == 'by_location':
        picking_items.sort(key=lambda x: x.get('location_code') or 'zzz')
    elif list_type == 'by_product':
        picking_items.sort(key=lambda x: x.get('sku_id', 0))

    # 4. 피킹리스트 생성
    now = datetime.now(timezone.utc)
    list_no = f"PL-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}"

    pl = picking_repo.create_picking_list({
        'list_no': list_no,
        'list_type': list_type,
        'warehouse_id': warehouse_id,
        'client_id': client_id,
        'status': 'created',
        'total_items': len(picking_items),
        'picked_items': 0,
        'created_by': created_by,
    })
    if not pl:
        raise RuntimeError('피킹리스트 생성 실패')

    pl_id = pl['id']

    # 5. 항목 삽입
    for item in picking_items:
        item['picking_list_id'] = pl_id
        if 'status' not in item:
            item['status'] = 'pending'
    picking_repo.create_picking_items(picking_items)

    # 6. 관련 주문 상태 → picking_ready
    for oid in order_ids:
        order = order_repo.get_order(oid)
        if order and order.get('status') in ('confirmed', 'pending'):
            order_repo.update_order_status(oid, 'picking_ready')

    pl['items'] = picking_items
    return pl
