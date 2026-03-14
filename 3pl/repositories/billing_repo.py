"""과금/정산 Repository."""
from .base import BaseRepository


class BillingRepository(BaseRepository):
    """요금제, 사용량, 청구서."""

    PLAN_TABLE = 'billing_plans'
    USAGE_TABLE = 'billing_usage'
    INVOICE_TABLE = 'billing_invoices'

    # ── 요금제 ──

    def list_plans(self):
        res = self.client.table(self.PLAN_TABLE).select('*').order('price').execute()
        return res.data or []

    def get_plan(self, plan_id):
        rows = self._query(self.PLAN_TABLE, filters=[('id', 'eq', plan_id)])
        return rows[0] if rows else None

    # ── 사용량 ──

    def log_usage(self, data):
        return self._insert(self.USAGE_TABLE, data)

    def get_monthly_usage(self, operator_id, year_month):
        return self._query(self.USAGE_TABLE, filters=[
            ('operator_id', 'eq', operator_id),
            ('year_month', 'eq', year_month),
        ])

    # ── 청구서 ──

    def create_invoice(self, data):
        return self._insert(self.INVOICE_TABLE, data)

    def list_invoices(self, status=None, limit=50):
        filters = [('status', 'eq', status)] if status else None
        return self._query(self.INVOICE_TABLE, filters=filters,
                           order_by='created_at', limit=limit)

    def update_invoice_status(self, invoice_id, status):
        return self._update(self.INVOICE_TABLE, invoice_id, {'status': status})

    def list_usage(self, year_month=None):
        filters = [('year_month', 'eq', year_month)] if year_month else None
        return self._query(self.USAGE_TABLE, filters=filters,
                           order_by='year_month')
