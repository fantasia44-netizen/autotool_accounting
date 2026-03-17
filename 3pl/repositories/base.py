"""Base Repository — Supabase 공통 CRUD + 연결 관리."""
import time

# soft delete 컬럼(is_deleted)이 있는 테이블 목록
SOFT_DELETE_TABLES = frozenset({
    'clients', 'client_rates', 'client_marketplace_credentials', 'skus',
})

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None  # supabase 미설치 시 데모 모드 전용


class BaseRepository:
    """모든 repository의 베이스 클래스.

    제공 기능:
    - Supabase 연결/재연결
    - 공통 CRUD 헬퍼 (query, insert, update, delete)
    - 테넌트 필터 자동 적용 (operator_id)
    - 연결 오류 자동 재시도
    """

    def __init__(self, client: Client, operator_id: int = None):
        self.client = client
        self.operator_id = operator_id
        self._url = None
        self._key = None

    def _apply_tenant_filter(self, query):
        """operator_id 기반 테넌트 필터 자동 적용."""
        if self.operator_id:
            return query.eq('operator_id', self.operator_id)
        return query

    def _retry_on_disconnect(self, fn, *args, **kwargs):
        """연결 오류 시 재연결 후 1회 재시도."""
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            err_msg = str(e).lower()
            if 'server disconnected' in err_msg or 'connection reset' in err_msg:
                self._reconnect()
                return fn(*args, **kwargs)
            raise

    def _reconnect(self):
        """Supabase 클라이언트 재생성."""
        if self._url and self._key:
            self.client = create_client(self._url, self._key)

    # ── 공통 CRUD 헬퍼 ──

    def _query(self, table, columns='*', filters=None, order_by=None,
               order_desc=True, limit=None, include_deleted=False,
               skip_tenant=False):
        """범용 조회. filters: [(col, op, val), ...]"""
        q = self.client.table(table).select(columns)
        if not skip_tenant:
            q = self._apply_tenant_filter(q)
        if not include_deleted and table in SOFT_DELETE_TABLES:
            q = q.or_('is_deleted.is.null,is_deleted.eq.false')
        if filters:
            for col, op, val in filters:
                if op == 'eq':
                    if val is None:
                        q = q.is_(col, 'null')
                    else:
                        q = q.eq(col, val)
                elif op == 'gte':
                    q = q.gte(col, val)
                elif op == 'lte':
                    q = q.lte(col, val)
                elif op == 'in':
                    q = q.in_(col, val)
                elif op == 'like':
                    q = q.like(col, val)
        if order_by:
            q = q.order(order_by, desc=order_desc)
        if limit:
            q = q.limit(limit)
        res = q.execute()
        return res.data or []

    # operator_id 컬럼이 없는 자식 테이블 (부모 FK로 이미 테넌트 분리됨)
    NO_TENANT_TABLES = frozenset({'order_items', 'picking_list_items'})

    def _insert(self, table, payload):
        """단건 삽입. Returns inserted row."""
        if self.operator_id and 'operator_id' not in payload \
                and table not in self.NO_TENANT_TABLES:
            payload['operator_id'] = self.operator_id
        res = self.client.table(table).insert(payload).execute()
        return res.data[0] if res.data else None

    def _update(self, table, record_id, payload):
        """ID 기반 업데이트 (테넌트 필터 적용)."""
        q = self.client.table(table).update(payload).eq('id', record_id)
        if table not in self.NO_TENANT_TABLES:
            q = self._apply_tenant_filter(q)
        res = q.execute()
        return res.data[0] if res.data else None

    def _delete(self, table, record_id):
        """ID 기반 소프트 삭제 (is_deleted 컬럼 있으면 soft, 없으면 hard).

        테넌트 필터 적용하여 타 운영사 데이터 삭제 방지.
        """
        from datetime import datetime, timezone
        # soft delete 시도
        try:
            q = self.client.table(table).update({
                'is_deleted': True,
                'deleted_at': datetime.now(timezone.utc).isoformat(),
            }).eq('id', record_id)
            q = self._apply_tenant_filter(q)
            res = q.execute()
            if res.data:
                return
        except Exception:
            pass  # is_deleted 컬럼 없으면 hard delete fallback

        # hard delete (테넌트 필터 적용)
        q = self.client.table(table).delete().eq('id', record_id)
        q = self._apply_tenant_filter(q)
        q.execute()

    def _upsert(self, table, payload, on_conflict='id'):
        """Upsert (insert or update)."""
        if self.operator_id and 'operator_id' not in payload:
            payload['operator_id'] = self.operator_id
        res = self.client.table(table).upsert(
            payload, on_conflict=on_conflict
        ).execute()
        return res.data[0] if res.data else None
