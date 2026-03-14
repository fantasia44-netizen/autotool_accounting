"""고객사별 마켓플레이스 API 인증정보 Repository."""
from .base import BaseRepository


class ClientMarketplaceRepository(BaseRepository):
    """고객사별 마켓플레이스 API 키 CRUD."""

    TABLE = 'client_marketplace_credentials'

    def list_credentials(self, client_id):
        """고객사별 연동 목록."""
        return self._query(self.TABLE,
                           filters=[('client_id', 'eq', client_id)],
                           order_by='channel', order_desc=False)

    def get_credential(self, cred_id):
        rows = self._query(self.TABLE, filters=[('id', 'eq', cred_id)])
        return rows[0] if rows else None

    def create_credential(self, data):
        return self._insert(self.TABLE, data)

    def update_credential(self, cred_id, data):
        return self._update(self.TABLE, cred_id, data)

    def delete_credential(self, cred_id):
        return self._delete(self.TABLE, cred_id)
