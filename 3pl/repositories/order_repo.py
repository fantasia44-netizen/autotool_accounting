"""주문/출고 관리 Repository."""
from .base import BaseRepository


class OrderRepository(BaseRepository):
    """주문, 주문상세, 출고, 배송."""

    ORDER_TABLE = 'orders'
    ORDER_ITEM_TABLE = 'order_items'
    SHIPMENT_TABLE = 'shipments'

    # ── 주문 ──

    def list_orders(self, status=None, client_id=None, channel=None,
                    date_from=None, date_to=None, search=None, limit=200):
        filters = []
        if status:
            filters.append(('status', 'eq', status))
        if client_id:
            filters.append(('client_id', 'eq', client_id))
        if channel:
            filters.append(('channel', 'eq', channel))
        if date_from:
            filters.append(('created_at', 'gte', date_from))
        if date_to:
            filters.append(('created_at', 'lte', date_to))
        if search:
            filters.append(('order_no', 'like', f'%{search}%'))
        return self._query(self.ORDER_TABLE, filters=filters or None,
                           order_by='created_at', limit=limit)

    def get_order(self, order_id):
        rows = self._query(self.ORDER_TABLE, filters=[('id', 'eq', order_id)])
        return rows[0] if rows else None

    def get_order_with_items(self, order_id):
        """주문 + 상세 아이템."""
        order = self.get_order(order_id)
        if order:
            order['items'] = self.get_order_items(order_id)
        return order

    def get_order_items(self, order_id):
        return self._query(self.ORDER_ITEM_TABLE,
                           filters=[('order_id', 'eq', order_id)],
                           skip_tenant=True)

    def create_order(self, order_data, items):
        order = self._insert(self.ORDER_TABLE, order_data)
        if order:
            for item in items:
                item['order_id'] = order['id']
                self._insert(self.ORDER_ITEM_TABLE, item)
        return order

    def update_order(self, order_id, data):
        return self._update(self.ORDER_TABLE, order_id, data)

    def update_order_status(self, order_id, status):
        return self._update(self.ORDER_TABLE, order_id, {'status': status})

    def count_by_status(self, client_id=None):
        """상태별 주문 건수 (client_id 필터 지원)."""
        filters = []
        if client_id:
            filters.append(('client_id', 'eq', client_id))
        rows = self._query(self.ORDER_TABLE, columns='id,status',
                           filters=filters or None)
        counts = {}
        for r in rows:
            s = r.get('status', 'unknown')
            counts[s] = counts.get(s, 0) + 1
        return counts

    def get_recent_orders(self, limit=10):
        return self._query(self.ORDER_TABLE, order_by='created_at', limit=limit)

    # ── 출고/배송 ──

    def create_shipment(self, data):
        return self._insert(self.SHIPMENT_TABLE, data)

    def get_shipment(self, shipment_id):
        rows = self._query(self.SHIPMENT_TABLE,
                           filters=[('id', 'eq', shipment_id)])
        return rows[0] if rows else None

    def list_shipments(self, order_id=None, status=None, shipment_type=None,
                       client_id=None, limit=200):
        filters = []
        if order_id:
            filters.append(('order_id', 'eq', order_id))
        if status:
            filters.append(('status', 'eq', status))
        if shipment_type:
            filters.append(('shipment_type', 'eq', shipment_type))
        if client_id:
            filters.append(('client_id', 'eq', client_id))
        return self._query(self.SHIPMENT_TABLE, filters=filters or None,
                           order_by='created_at', limit=limit)

    def update_shipment(self, shipment_id, data):
        return self._update(self.SHIPMENT_TABLE, shipment_id, data)

    def update_shipment_status(self, shipment_id, status):
        return self._update(self.SHIPMENT_TABLE, shipment_id, {'status': status})

    def count_shipments_by_status(self):
        rows = self._query(self.SHIPMENT_TABLE, columns='id,status')
        counts = {}
        for r in rows:
            s = r.get('status', 'unknown')
            counts[s] = counts.get(s, 0) + 1
        return counts

    def search_by_invoice(self, invoice_no):
        """송장번호로 출고 검색."""
        return self._query(self.SHIPMENT_TABLE,
                           filters=[('invoice_no', 'like', f'%{invoice_no}%')],
                           limit=10)

    # ── 주문 보류/차단 ──

    def hold_order(self, order_id, reason, user_id):
        """주문 보류 처리."""
        from datetime import datetime, timezone
        return self._update(self.ORDER_TABLE, order_id, {
            'hold_flag': True,
            'hold_reason': reason,
            'hold_by': user_id,
            'hold_at': datetime.now(timezone.utc).isoformat(),
        })

    def release_hold(self, order_id):
        """보류 해제."""
        return self._update(self.ORDER_TABLE, order_id, {
            'hold_flag': False,
            'hold_reason': None,
            'hold_by': None,
            'hold_at': None,
        })

    # ── 상태 로그 ──

    STATUS_LOG_TABLE = 'order_status_logs'

    def log_status_change(self, order_id, old_status, new_status,
                          changed_by=None, reason=None):
        """주문 상태 변경 이력 기록."""
        return self._insert(self.STATUS_LOG_TABLE, {
            'order_id': order_id,
            'old_status': old_status,
            'new_status': new_status,
            'changed_by': changed_by,
            'reason': reason,
        })

    def get_status_logs(self, order_id):
        """주문 상태 변경 이력 조회."""
        return self._query(self.STATUS_LOG_TABLE,
                           filters=[('order_id', 'eq', order_id)],
                           order_by='created_at', order_desc=True)
