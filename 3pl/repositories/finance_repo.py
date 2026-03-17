"""경영분석 (Finance) Repository.

비용 관리, 월별 손익 집계.
"""
from .base import BaseRepository


class FinanceRepository(BaseRepository):
    """expenses, monthly_pnl 테이블 CRUD."""

    EXPENSE_TABLE = 'expenses'
    PNL_TABLE = 'monthly_pnl'

    # ── 비용(Expense) ──

    def create_expense(self, data):
        return self._insert(self.EXPENSE_TABLE, data)

    def update_expense(self, expense_id, data):
        return self._update(self.EXPENSE_TABLE, expense_id, data)

    def delete_expense(self, expense_id):
        return self._delete(self.EXPENSE_TABLE, expense_id)

    def get_expense(self, expense_id):
        rows = self._query(self.EXPENSE_TABLE, filters=[
            ('id', 'eq', expense_id),
        ])
        return rows[0] if rows else None

    def list_expenses(self, year_month=None, category=None, limit=500):
        filters = []
        if year_month:
            filters.append(('year_month', 'eq', year_month))
        if category:
            filters.append(('category', 'eq', category))
        return self._query(self.EXPENSE_TABLE, filters=filters or None,
                           order_by='expense_date', order_desc=True, limit=limit)

    def sum_expenses_by_month(self, year_month):
        """월별 비용 카테고리 합산."""
        rows = self.list_expenses(year_month=year_month)
        by_cat = {}
        total = 0
        for r in rows:
            cat = r.get('category', 'etc')
            amt = float(r.get('amount', 0))
            by_cat[cat] = by_cat.get(cat, 0) + amt
            total += amt
        return {'by_category': by_cat, 'total': total, 'items': rows}

    # ── 월별 P&L ──

    def get_pnl(self, year_month):
        rows = self._query(self.PNL_TABLE, filters=[
            ('year_month', 'eq', year_month),
        ])
        return rows[0] if rows else None

    def upsert_pnl(self, data):
        return self._upsert(self.PNL_TABLE, data, on_conflict='operator_id,year_month')

    def list_pnl(self, limit=12):
        """최근 N개월 P&L."""
        return self._query(self.PNL_TABLE, order_by='year_month',
                           order_desc=True, limit=limit)
