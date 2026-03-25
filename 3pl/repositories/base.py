"""Base Repository — Supabase 공통 CRUD + 연결 관리 + 감사 로그."""
import time

# soft delete 컬럼(is_deleted)이 있는 테이블 목록
SOFT_DELETE_TABLES = frozenset({
    'clients', 'client_rates', 'client_marketplace_credentials', 'skus',
    'orders', 'shipments', 'packing_jobs', 'inbound_receipts',
    'inventory_adjustments', 'client_billing_logs', 'client_invoices',
    'picking_lists', 'expenses',
})

# 감사 로그 제외 테이블 (로그 자체, 임시 데이터 등)
AUDIT_EXCLUDE_TABLES = frozenset({
    'audit_logs', 'failed_billing_events', 'monthly_pnl',
    'daily_inventory_snapshots',
})

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None  # supabase 미설치 시 데모 모드 전용


def _get_current_user_info():
    """Flask 요청 컨텍스트에서 현재 사용자 정보 추출."""
    try:
        from flask import request, has_request_context
        from flask_login import current_user
        if has_request_context() and hasattr(current_user, 'id') and current_user.is_authenticated:
            return {
                'user_id': current_user.id,
                'user_name': getattr(current_user, 'name', '') or getattr(current_user, 'username', ''),
                'ip_address': request.remote_addr,
            }
    except Exception:
        pass
    return {'user_id': None, 'user_name': 'system', 'ip_address': None}


class BaseRepository:
    """모든 repository의 베이스 클래스.

    제공 기능:
    - Supabase 연결/재연결
    - 공통 CRUD 헬퍼 (query, insert, update, delete)
    - 테넌트 필터 자동 적용 (operator_id)
    - 연결 오류 자동 재시도
    - 감사 로그 자동 기록 (CUD 작업)
    - soft delete 일괄 적용
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

    # ── 감사 로그 ──

    def _audit_log(self, action, table, record_id=None,
                   before_data=None, after_data=None, memo=None):
        """감사 로그 비동기 기록 (실패해도 비즈니스 로직 중단 안 함)."""
        if table in AUDIT_EXCLUDE_TABLES:
            return
        try:
            import json
            user_info = _get_current_user_info()
            payload = {
                'operator_id': self.operator_id,
                'user_id': user_info['user_id'],
                'user_name': user_info['user_name'],
                'action': action,
                'table_name': table,
                'record_id': str(record_id) if record_id else None,
                'before_data': json.dumps(before_data, ensure_ascii=False, default=str) if before_data else None,
                'after_data': json.dumps(after_data, ensure_ascii=False, default=str) if after_data else None,
                'ip_address': user_info['ip_address'],
                'memo': memo,
            }
            self.client.table('audit_logs').insert(payload).execute()
        except Exception:
            pass  # 감사 로그 실패가 비즈니스 로직 중단하면 안 됨

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
                elif op == 'neq':
                    q = q.neq(col, val)
                elif op == 'lt':
                    q = q.lt(col, val)
                elif op == 'gt':
                    q = q.gt(col, val)
        if order_by:
            q = q.order(order_by, desc=order_desc)
        if limit:
            q = q.limit(limit)
        res = q.execute()
        return res.data or []

    # operator_id 컬럼이 없는 자식 테이블 (부모 FK로 이미 테넌트 분리됨)
    NO_TENANT_TABLES = frozenset({
        'order_items', 'picking_list_items',
        'warehouse_zones', 'warehouse_locations',
    })

    def _insert(self, table, payload):
        """단건 삽입 + 감사 로그. Returns inserted row."""
        if self.operator_id and 'operator_id' not in payload \
                and table not in self.NO_TENANT_TABLES:
            payload['operator_id'] = self.operator_id
        res = self.client.table(table).insert(payload).execute()
        row = res.data[0] if res.data else None
        if row:
            self._audit_log('create', table, record_id=row.get('id'),
                            after_data=row)
        return row

    def _update(self, table, record_id, payload):
        """ID 기반 업데이트 + 감사 로그 (before/after 스냅샷)."""
        # before 스냅샷 조회 (tenant 필터 적용)
        before = None
        if table not in AUDIT_EXCLUDE_TABLES:
            try:
                q = self.client.table(table).select('*').eq('id', record_id)
                if table not in self.NO_TENANT_TABLES:
                    q = self._apply_tenant_filter(q)
                res = q.execute()
                before = res.data[0] if res.data else None
            except Exception:
                pass
        # 업데이트 실행
        q = self.client.table(table).update(payload).eq('id', record_id)
        if table not in self.NO_TENANT_TABLES:
            q = self._apply_tenant_filter(q)
        res = q.execute()
        after = res.data[0] if res.data else None
        if after:
            self._audit_log('update', table, record_id=record_id,
                            before_data=before, after_data=after)
        return after

    def _delete(self, table, record_id, deleted_by=None):
        """ID 기반 삭제 — soft delete 우선, 불가 시 hard delete.

        deleted_by: 삭제 수행자 user_id (soft delete 시 기록).
        """
        from datetime import datetime, timezone
        try:
            from services.tz_utils import now_kst
            ts = now_kst().isoformat()
        except ImportError:
            ts = datetime.now(timezone.utc).isoformat()

        # before 스냅샷 (tenant 필터 적용)
        before = None
        try:
            q = self.client.table(table).select('*').eq('id', record_id)
            if table not in self.NO_TENANT_TABLES:
                q = self._apply_tenant_filter(q)
            res = q.execute()
            before = res.data[0] if res.data else None
        except Exception:
            pass

        # soft delete 대상 테이블이면 soft delete
        if table in SOFT_DELETE_TABLES:
            soft_payload = {
                'is_deleted': True,
                'deleted_at': ts,
            }
            if deleted_by:
                soft_payload['deleted_by'] = deleted_by
            elif before:
                user_info = _get_current_user_info()
                if user_info['user_id']:
                    soft_payload['deleted_by'] = user_info['user_id']
            try:
                q = self.client.table(table).update(soft_payload).eq('id', record_id)
                q = self._apply_tenant_filter(q)
                res = q.execute()
                if res.data:
                    self._audit_log('delete', table, record_id=record_id,
                                    before_data=before, memo='soft_delete')
                    return
            except Exception:
                pass  # fallback to hard delete

        # hard delete (테넌트 필터 적용)
        q = self.client.table(table).delete().eq('id', record_id)
        q = self._apply_tenant_filter(q)
        q.execute()
        self._audit_log('delete', table, record_id=record_id,
                        before_data=before, memo='hard_delete')

    # 부모-자식 관계 (복원 시 부모 존재 검증용)
    _PARENT_REFS = {
        'skus': ('clients', 'client_id'),
        'orders': ('clients', 'client_id'),
        'shipments': ('orders', 'order_id'),
        'client_rates': ('clients', 'client_id'),
        'client_billing_logs': ('clients', 'client_id'),
        'client_invoices': ('clients', 'client_id'),
        'client_marketplace_credentials': ('clients', 'client_id'),
        'picking_lists': ('orders', None),  # order_id 없을 수 있음
    }

    def _restore(self, table, record_id):
        """soft delete된 레코드 복원 (부모 참조 무결성 검증 포함)."""
        if table not in SOFT_DELETE_TABLES:
            return None

        # 부모 테이블 존재 확인
        parent_ref = self._PARENT_REFS.get(table)
        if parent_ref:
            parent_table, fk_col = parent_ref
            if fk_col:
                # 복원 대상 레코드 조회 (삭제된 상태이므로 include_deleted=True)
                record = self._query(table, filters=[('id', 'eq', record_id)],
                                     include_deleted=True)
                if record and record[0].get(fk_col):
                    parent_id = record[0][fk_col]
                    parent = self._query(parent_table,
                                         filters=[('id', 'eq', parent_id)])
                    if not parent:
                        raise ValueError(
                            f'부모 레코드가 삭제된 상태입니다 '
                            f'({parent_table} id={parent_id}). '
                            f'부모를 먼저 복원하세요.')

        q = self.client.table(table).update({
            'is_deleted': False,
            'deleted_at': None,
            'deleted_by': None,
        }).eq('id', record_id)
        if table not in self.NO_TENANT_TABLES:
            q = self._apply_tenant_filter(q)
        res = q.execute()
        restored = res.data[0] if res.data else None
        if restored:
            self._audit_log('restore', table, record_id=record_id,
                            after_data=restored)
        return restored

    def _upsert(self, table, payload, on_conflict='id'):
        """Upsert (insert or update)."""
        if self.operator_id and 'operator_id' not in payload:
            payload['operator_id'] = self.operator_id
        res = self.client.table(table).upsert(
            payload, on_conflict=on_conflict
        ).execute()
        row = res.data[0] if res.data else None
        if row:
            self._audit_log('upsert', table, record_id=row.get('id'),
                            after_data=row)
        return row
