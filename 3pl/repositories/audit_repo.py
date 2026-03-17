"""감사 로그 (Audit Log) Repository.

모든 CUD 작업의 이력을 추적하여 admin이 조회/복원 가능.
"""
from .base import BaseRepository


class AuditRepository(BaseRepository):
    """audit_logs 테이블 CRUD."""

    TABLE = 'audit_logs'

    def log(self, action, table_name, record_id=None,
            before_data=None, after_data=None,
            user_id=None, user_name=None, ip_address=None, memo=None):
        """감사 로그 1건 기록."""
        import json
        payload = {
            'action': action,
            'table_name': table_name,
            'record_id': str(record_id) if record_id else None,
            'before_data': json.dumps(before_data, ensure_ascii=False, default=str) if before_data else None,
            'after_data': json.dumps(after_data, ensure_ascii=False, default=str) if after_data else None,
            'user_id': user_id,
            'user_name': user_name or '',
            'ip_address': ip_address,
            'memo': memo,
        }
        try:
            return self._insert(self.TABLE, payload)
        except Exception:
            pass  # 감사 로그 실패가 비즈니스 로직 중단하면 안 됨

    def list_logs(self, table_name=None, record_id=None,
                  action=None, user_id=None,
                  date_from=None, date_to=None,
                  limit=200, offset=0):
        """감사 로그 목록 조회."""
        filters = []
        if table_name:
            filters.append(('table_name', 'eq', table_name))
        if record_id:
            filters.append(('record_id', 'eq', str(record_id)))
        if action:
            filters.append(('action', 'eq', action))
        if user_id:
            filters.append(('user_id', 'eq', user_id))
        if date_from:
            filters.append(('created_at', 'gte', date_from))
        if date_to:
            filters.append(('created_at', 'lte', date_to))
        return self._query(self.TABLE, filters=filters or None,
                           order_by='created_at', order_desc=True,
                           limit=limit)

    def get_record_history(self, table_name, record_id, limit=50):
        """특정 레코드의 변경 이력."""
        return self._query(self.TABLE, filters=[
            ('table_name', 'eq', table_name),
            ('record_id', 'eq', str(record_id)),
        ], order_by='created_at', order_desc=True, limit=limit)
