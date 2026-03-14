"""고객사 과금/정산 Repository."""
from .base import BaseRepository


class ClientBillingRepository(BaseRepository):
    """과금 로그, 정산서 CRUD."""

    LOG_TABLE = 'client_billing_logs'
    INVOICE_TABLE = 'client_invoices'

    # ── 과금 로그 ──

    def log_fee(self, data):
        return self._insert(self.LOG_TABLE, data)

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
