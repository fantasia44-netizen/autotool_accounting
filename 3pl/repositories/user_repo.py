"""사용자 관리 Repository."""
from .base import BaseRepository


class UserRepository(BaseRepository):
    """사용자 CRUD + 승인 관리."""

    TABLE = 'users'

    def list_users(self, role=None, is_approved=None):
        filters = []
        if role:
            filters.append(('role', 'eq', role))
        if is_approved is not None:
            filters.append(('is_approved', 'eq', is_approved))
        return self._query(self.TABLE, filters=filters or None,
                           order_by='created_at')

    def get_user(self, user_id):
        rows = self._query(self.TABLE, filters=[('id', 'eq', user_id)])
        return rows[0] if rows else None

    def get_by_username(self, username):
        rows = self._query(self.TABLE,
                           filters=[('username', 'eq', username)])
        return rows[0] if rows else None

    def create_user(self, data):
        return self._insert(self.TABLE, data)

    def update_user(self, user_id, data):
        return self._update(self.TABLE, user_id, data)

    def approve_user(self, user_id):
        return self._update(self.TABLE, user_id, {'is_approved': True})

    def deactivate_user(self, user_id):
        return self._update(self.TABLE, user_id, {'is_active': False})

    def list_pending_approvals(self):
        return self._query(self.TABLE,
                           filters=[('is_approved', 'eq', False),
                                    ('is_active', 'eq', True)],
                           order_by='created_at')

    def list_by_client(self, client_id):
        return self._query(self.TABLE,
                           filters=[('client_id', 'eq', client_id)],
                           order_by='name', order_desc=False)
