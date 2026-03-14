"""창고 관리 서비스 — 입고/출고 프로세스."""
from db_utils import get_repo


def process_inbound(inv_repo, sku_id, location_id, quantity,
                    lot_number=None, memo='', user_id=None):
    """입고 처리: 재고 증가 + 이력 기록."""
    stock = inv_repo.get_stock(sku_id, location_id, lot_number)
    current_qty = stock['quantity'] if stock else 0

    inv_repo.upsert_stock({
        'sku_id': sku_id,
        'location_id': location_id,
        'quantity': current_qty + quantity,
        'lot_number': lot_number,
    })

    inv_repo.log_movement({
        'sku_id': sku_id,
        'location_id': location_id,
        'movement_type': 'inbound',
        'quantity': quantity,
        'lot_number': lot_number,
        'memo': memo or '입고',
        'user_id': user_id,
    })


def process_outbound(order_id, items, user_id=None):
    """출고 처리: 재고 차감 + 출고 이력."""
    inv_repo = get_repo('inventory')
    order_repo = get_repo('order')

    for item in items:
        stock = inv_repo.get_stock(item['sku_id'], item['location_id'])
        if not stock or stock['quantity'] < item['quantity']:
            raise ValueError(f"재고 부족: SKU {item['sku_id']}")

        inv_repo.upsert_stock({
            'sku_id': item['sku_id'],
            'location_id': item['location_id'],
            'quantity': stock['quantity'] - item['quantity'],
        })

        inv_repo.log_movement({
            'sku_id': item['sku_id'],
            'location_id': item['location_id'],
            'movement_type': 'outbound',
            'quantity': -item['quantity'],
            'order_id': order_id,
            'user_id': user_id,
        })

    order_repo.update_order_status(order_id, 'shipped')
