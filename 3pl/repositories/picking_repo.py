"""피킹리스트 Repository."""
from .base import BaseRepository


class PickingRepository(BaseRepository):
    """피킹리스트 및 피킹 항목 CRUD."""

    LIST_TABLE = 'picking_lists'
    ITEM_TABLE = 'picking_list_items'

    # ── 피킹리스트 ──

    def create_picking_list(self, data):
        return self._insert(self.LIST_TABLE, data)

    def get_picking_list(self, list_id):
        rows = self._query(self.LIST_TABLE, filters=[('id', 'eq', list_id)])
        return rows[0] if rows else None

    def get_picking_list_with_items(self, list_id):
        pl = self.get_picking_list(list_id)
        if pl:
            pl['items'] = self.get_items(list_id)
        return pl

    def list_picking_lists(self, status=None, warehouse_id=None,
                           client_id=None, date_from=None, limit=100):
        filters = []
        if status:
            filters.append(('status', 'eq', status))
        if warehouse_id:
            filters.append(('warehouse_id', 'eq', warehouse_id))
        if client_id:
            filters.append(('client_id', 'eq', client_id))
        if date_from:
            filters.append(('created_at', 'gte', date_from))
        return self._query(self.LIST_TABLE, filters=filters or None,
                           order_by='created_at', limit=limit)

    def update_picking_list(self, list_id, data):
        return self._update(self.LIST_TABLE, list_id, data)

    # ── 피킹 항목 ──

    def create_picking_item(self, data):
        return self._insert(self.ITEM_TABLE, data)

    def create_picking_items(self, items):
        """여러 항목 일괄 삽입."""
        results = []
        for item in items:
            r = self._insert(self.ITEM_TABLE, item)
            if r:
                results.append(r)
        return results

    def get_items(self, list_id):
        return self._query(self.ITEM_TABLE,
                           filters=[('picking_list_id', 'eq', list_id)],
                           order_by='location_code', order_desc=False)

    def get_item(self, item_id):
        rows = self._query(self.ITEM_TABLE, filters=[('id', 'eq', item_id)])
        return rows[0] if rows else None

    def update_item(self, item_id, data):
        return self._update(self.ITEM_TABLE, item_id, data)

    def update_item_picked(self, item_id, picked_qty):
        """피킹 수량 갱신 + 상태 전이."""
        from datetime import datetime, timezone
        item = self.get_item(item_id)
        if not item:
            return None

        status = 'picked' if picked_qty >= item.get('expected_qty', 0) else 'pending'
        if picked_qty > 0 and picked_qty < item.get('expected_qty', 0):
            status = 'short'

        return self._update(self.ITEM_TABLE, item_id, {
            'picked_qty': picked_qty,
            'status': status,
            'picked_at': datetime.now(timezone.utc).isoformat() if status == 'picked' else None,
        })

    def complete_picking_list(self, list_id):
        """피킹리스트 완료 처리."""
        from datetime import datetime, timezone
        items = self.get_items(list_id)
        picked_count = sum(1 for it in items if it.get('status') == 'picked')
        return self._update(self.LIST_TABLE, list_id, {
            'status': 'completed',
            'picked_items': picked_count,
            'completed_at': datetime.now(timezone.utc).isoformat(),
        })

    def count_by_status(self):
        rows = self._query(self.LIST_TABLE, columns='id,status')
        counts = {}
        for r in rows:
            s = r.get('status', 'unknown')
            counts[s] = counts.get(s, 0) + 1
        return counts
