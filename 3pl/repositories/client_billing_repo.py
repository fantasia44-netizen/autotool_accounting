"""고객사 과금/정산 Repository."""
from .base import BaseRepository


class ClientBillingRepository(BaseRepository):
    """과금 로그, 정산서 CRUD."""

    LOG_TABLE = 'client_billing_logs'
    INVOICE_TABLE = 'client_invoices'

    # ── 과금 로그 ──

    def log_fee(self, data):
        return self._insert(self.LOG_TABLE, data)

    def find_by_dedupe_key(self, client_id, dedupe_key):
        """dedupe_key로 기존 과금 로그 조회. 있으면 row 반환, 없으면 None."""
        rows = self._query(self.LOG_TABLE, filters=[
            ('client_id', 'eq', client_id),
            ('dedupe_key', 'eq', dedupe_key),
        ], limit=1)
        return rows[0] if rows else None

    def log_fee_idempotent(self, data):
        """중복방지 과금 기록. dedupe_key가 있으면 중복 체크 후 insert.

        Returns:
            (row, is_new) — is_new=False이면 기존 row 반환(스킵됨).
        """
        dedupe_key = data.get('dedupe_key')
        if dedupe_key:
            existing = self.find_by_dedupe_key(data.get('client_id'), dedupe_key)
            if existing:
                return existing, False
        row = self._insert(self.LOG_TABLE, data)
        return row, True

    def delete_fee(self, fee_id):
        return self._delete(self.LOG_TABLE, fee_id)

    def list_fees(self, client_id, year_month=None, category=None, limit=500):
        filters = [('client_id', 'eq', client_id)]
        if year_month:
            filters.append(('year_month', 'eq', year_month))
        if category:
            filters.append(('category', 'eq', category))
        return self._query(self.LOG_TABLE, filters=filters,
                           order_by='created_at', limit=limit)

    def get_monthly_summary(self, client_id, year_month):
        """카테고리별 소계."""
        rows = self.list_fees(client_id, year_month=year_month)
        summary = {}
        total = 0
        for r in rows:
            cat = r.get('category', 'custom')
            amt = float(r.get('total_amount', 0))
            summary[cat] = summary.get(cat, 0) + amt
            total += amt
        return {'by_category': summary, 'total': total, 'items': rows}

    def get_bulk_monthly_totals(self, year_month):
        """전 고객 월매출 일괄 조회 (N+1 제거용, 1회 쿼리).

        Returns: {client_id: total_amount, ...}
        """
        rows = self._query(self.LOG_TABLE,
                           columns='client_id,total_amount',
                           filters=[('year_month', 'eq', year_month)])
        totals = {}
        for r in rows:
            cid = r.get('client_id')
            amt = float(r.get('total_amount', 0))
            totals[cid] = totals.get(cid, 0) + amt
        return totals

    # ── 정산서 ──

    def get_invoice(self, client_id, year_month):
        rows = self._query(self.INVOICE_TABLE, filters=[
            ('client_id', 'eq', client_id),
            ('year_month', 'eq', year_month),
        ])
        return rows[0] if rows else None

    def create_invoice(self, data):
        return self._insert(self.INVOICE_TABLE, data)

    def update_invoice(self, invoice_id, data):
        return self._update(self.INVOICE_TABLE, invoice_id, data)

    def list_invoices(self, client_id=None, status=None, limit=100):
        filters = []
        if client_id:
            filters.append(('client_id', 'eq', client_id))
        if status:
            filters.append(('status', 'eq', status))
        return self._query(self.INVOICE_TABLE, filters=filters or None,
                           order_by='created_at', order_desc=True, limit=limit)

    # ── 과금 실패 이벤트 (DLQ) ──

    FAILED_TABLE = 'failed_billing_events'

    def list_failed_events(self, status='pending', limit=200):
        filters = [('status', 'eq', status)] if status else None
        return self._query(self.FAILED_TABLE, filters=filters,
                           order_by='created_at', order_desc=True, limit=limit)

    def get_failed_event(self, event_id):
        rows = self._query(self.FAILED_TABLE, filters=[('id', 'eq', event_id)])
        return rows[0] if rows else None

    def update_failed_event(self, event_id, data):
        return self._update(self.FAILED_TABLE, event_id, data)
