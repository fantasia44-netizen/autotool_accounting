"""고객사 요금표 Repository."""
from .base import BaseRepository


class ClientRateRepository(BaseRepository):
    """고객사별 커스텀 요금 항목 CRUD."""

    TABLE = 'client_rates'
    MAX_RATES_PER_CLIENT = 20

    def list_rates(self, client_id):
        """고객사별 요금 목록 (sort_order 오름차순)."""
        return self._query(self.TABLE,
                           filters=[('client_id', 'eq', client_id)],
                           order_by='sort_order', order_desc=False)

    def get_rate(self, rate_id):
        rows = self._query(self.TABLE, filters=[('id', 'eq', rate_id)])
        return rows[0] if rows else None

    def create_rate(self, data):
        return self._insert(self.TABLE, data)

    def update_rate(self, rate_id, data):
        return self._update(self.TABLE, rate_id, data)

    def delete_rate(self, rate_id):
        return self._delete(self.TABLE, rate_id)

    def count_rates(self, client_id):
        """고객사별 요금 항목 수 (최대 20개 제한용)."""
        rows = self._query(self.TABLE,
                           columns='id',
                           filters=[('client_id', 'eq', client_id)])
        return len(rows)
