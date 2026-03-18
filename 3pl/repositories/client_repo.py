"""고객사(화주) Repository."""
from .base import BaseRepository


class ClientRepository(BaseRepository):
    """고객사 CRUD + 통계."""

    TABLE = 'clients'

    def list_clients(self, is_active=True):
        filters = [('is_active', 'eq', is_active)] if is_active is not None else None
        return self._query(self.TABLE, filters=filters,
                           order_by='name', order_desc=False)

    def get_client(self, client_id):
        rows = self._query(self.TABLE, filters=[('id', 'eq', client_id)])
        return rows[0] if rows else None

    def create_client(self, data):
        return self._insert(self.TABLE, data)

    def update_client(self, client_id, data):
        return self._update(self.TABLE, client_id, data)

    def deactivate_client(self, client_id):
        return self._update(self.TABLE, client_id, {'is_active': False})

    def search_clients(self, keyword):
        """이름/사업자번호로 검색."""
        return self._query(self.TABLE,
                           filters=[('name', 'like', f'%{keyword}%')],
                           order_by='name', order_desc=False)

    def soft_delete_client_cascade(self, client_id):
        """고객사 소프트 삭제 + 연관 데이터 캐스케이드 삭제.

        삭제 대상: clients, skus, client_rates, client_marketplace_credentials
        보존 대상: orders, shipments, client_billing_logs (이력 보존)
        """
        # 1. 자식 테이블 soft delete
        cascade_tables = ['skus', 'client_rates', 'client_marketplace_credentials']
        for table in cascade_tables:
            rows = self._query(table, filters=[('client_id', 'eq', client_id)])
            for row in rows:
                try:
                    self._delete(table, row['id'])
                except Exception:
                    pass  # 개별 실패는 스킵

        # 2. 부모(clients) soft delete
        self._delete(self.TABLE, client_id)
