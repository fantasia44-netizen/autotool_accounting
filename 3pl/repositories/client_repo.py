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
