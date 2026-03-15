"""재고 관리 Repository."""
from .base import BaseRepository


class InventoryRepository(BaseRepository):
    """SKU, 재고, 입출고 이력."""

    SKU_TABLE = 'skus'
    STOCK_TABLE = 'inventory_stock'
    MOVEMENT_TABLE = 'inventory_movements'

    # ── SKU ──

    def list_skus(self, client_id=None, category=None, search=None):
        filters = []
        if client_id:
            filters.append(('client_id', 'eq', client_id))
        if category:
            filters.append(('category', 'eq', category))
        if search:
            filters.append(('name', 'like', f'%{search}%'))
        return self._query(self.SKU_TABLE, filters=filters or None,
                           order_by='sku_code', order_desc=False)

    def get_sku(self, sku_id):
        rows = self._query(self.SKU_TABLE, filters=[('id', 'eq', sku_id)])
        return rows[0] if rows else None

    def get_sku_by_code(self, sku_code):
        rows = self._query(self.SKU_TABLE,
                           filters=[('sku_code', 'eq', sku_code)])
        return rows[0] if rows else None

    def get_sku_by_barcode(self, barcode):
        rows = self._query(self.SKU_TABLE,
                           filters=[('barcode', 'eq', barcode)])
        return rows[0] if rows else None

    def create_sku(self, data):
        return self._insert(self.SKU_TABLE, data)

    def update_sku(self, sku_id, data):
        return self._update(self.SKU_TABLE, sku_id, data)

    def count_skus(self, client_id=None):
        filters = [('client_id', 'eq', client_id)] if client_id else None
        rows = self._query(self.SKU_TABLE, columns='id', filters=filters)
        return len(rows)

    # ── 재고 ──

    def get_stock(self, sku_id, location_id, lot_number=None):
        filters = [
            ('sku_id', 'eq', sku_id),
            ('location_id', 'eq', location_id),
        ]
        if lot_number:
            filters.append(('lot_number', 'eq', lot_number))
        rows = self._query(self.STOCK_TABLE, filters=filters)
        return rows[0] if rows else None

    def list_stock(self, sku_id=None, location_id=None):
        filters = []
        if sku_id:
            filters.append(('sku_id', 'eq', sku_id))
        if location_id:
            filters.append(('location_id', 'eq', location_id))
        return self._query(self.STOCK_TABLE, filters=filters or None,
                           order_by='updated_at')

    def list_stock_by_sku(self, sku_id):
        return self._query(self.STOCK_TABLE,
                           filters=[('sku_id', 'eq', sku_id)])

    def list_all_stock(self):
        """전체 재고 현황 (테넌트 필터 적용)."""
        return self._query(self.STOCK_TABLE, order_by='sku_id', order_desc=False)

    def upsert_stock(self, data):
        return self._upsert(self.STOCK_TABLE, data,
                            on_conflict='sku_id,location_id,lot_number')

    def adjust_stock(self, sku_id, location_id, delta, lot_number=None):
        """재고 수량 조정 (+/-)."""
        stock = self.get_stock(sku_id, location_id, lot_number)
        if stock:
            new_qty = stock['quantity'] + delta
            return self._update(self.STOCK_TABLE, stock['id'],
                                {'quantity': new_qty})
        elif delta > 0:
            return self._insert(self.STOCK_TABLE, {
                'sku_id': sku_id,
                'location_id': location_id,
                'quantity': delta,
                'lot_number': lot_number,
            })
        return None

    def get_low_stock_items(self, threshold=10):
        """부족 재고 목록 (SKU별 min_stock_qty 우선, 없으면 threshold)."""
        stocks = self.list_all_stock()
        skus = self.list_skus() or []
        sku_map = {s['id']: s for s in skus}

        # SKU별 재고 합산
        sku_totals = {}
        for st in stocks:
            sid = st.get('sku_id')
            sku_totals[sid] = sku_totals.get(sid, 0) + st.get('quantity', 0)

        low_items = []
        for sid, qty in sku_totals.items():
            sku = sku_map.get(sid, {})
            min_qty = sku.get('min_stock_qty') or threshold
            if qty <= min_qty:
                low_items.append({
                    'sku_id': sid,
                    'sku_code': sku.get('sku_code', ''),
                    'sku_name': sku.get('name', ''),
                    'client_id': sku.get('client_id'),
                    'quantity': qty,
                    'min_stock_qty': min_qty,
                    'storage_temp': sku.get('storage_temp', 'ambient'),
                })
        return low_items

    def get_expiring_soon(self, days=30):
        """유통기한 임박 재고 (days일 이내)."""
        from datetime import datetime, timedelta
        cutoff = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
        return self._query(self.STOCK_TABLE,
                           filters=[('expiry_date', 'lte', cutoff)],
                           order_by='expiry_date', order_desc=False)

    def get_expired_stock(self):
        """유통기한 만료 재고 (오늘 기준)."""
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        return self._query(self.STOCK_TABLE,
                           filters=[('expiry_date', 'lte', today)],
                           order_by='expiry_date', order_desc=False)

    # ── 재고 예약 ──

    RESERVATION_TABLE = 'inventory_reservations'

    def update_reserved_qty(self, stock_id, new_reserved_qty):
        """재고 레코드의 reserved_qty 갱신."""
        return self._update(self.STOCK_TABLE, stock_id,
                            {'reserved_qty': new_reserved_qty})

    def create_reservation(self, data):
        """예약 내역 생성."""
        return self._insert(self.RESERVATION_TABLE, data)

    def list_reservations(self, order_id, status=None):
        """주문별 예약 내역 조회."""
        filters = [('order_id', 'eq', order_id)]
        if status:
            filters.append(('status', 'eq', status))
        return self._query(self.RESERVATION_TABLE, filters=filters)

    def update_reservation_status(self, reservation_id, status,
                                   committed_at=None):
        """예약 상태 변경."""
        data = {'status': status}
        if committed_at:
            data['committed_at'] = committed_at
        return self._update(self.RESERVATION_TABLE, reservation_id, data)

    # ── 입출고 이력 (수불장) ──

    def log_movement(self, data):
        return self._insert(self.MOVEMENT_TABLE, data)

    def list_movements(self, sku_id=None, movement_type=None,
                       date_from=None, date_to=None, limit=200):
        filters = []
        if sku_id:
            filters.append(('sku_id', 'eq', sku_id))
        if movement_type:
            filters.append(('movement_type', 'eq', movement_type))
        if date_from:
            filters.append(('created_at', 'gte', date_from))
        if date_to:
            filters.append(('created_at', 'lte', date_to))
        return self._query(self.MOVEMENT_TABLE, filters=filters or None,
                           order_by='created_at', limit=limit)

    def get_movement_summary(self):
        """유형별 이동 요약."""
        rows = self._query(self.MOVEMENT_TABLE, order_by='created_at')
        summary = {}
        for r in rows:
            mt = r.get('movement_type', 'unknown')
            if mt not in summary:
                summary[mt] = {'count': 0, 'total_qty': 0}
            summary[mt]['count'] += 1
            summary[mt]['total_qty'] += abs(r.get('quantity', 0))
        return summary
