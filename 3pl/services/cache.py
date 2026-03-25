"""경량 인메모리 TTL 캐시 — 대시보드 성능 최적화용.

외부 의존성 없음. SaaS 확장 시 Redis로 교체 가능.
프로세스 단위 캐시이므로 gunicorn worker 간 공유 안 됨 (OK for now).

사용법:
    from services.cache import dashboard_cache

    # 캐시 조회/저장
    data = dashboard_cache.get('operator:1:kpi')
    if data is None:
        data = expensive_query()
        dashboard_cache.set('operator:1:kpi', data, ttl=60)

    # 특정 패턴 무효화
    dashboard_cache.invalidate('operator:1:')
"""
import time
import threading


class TTLCache:
    """Thread-safe 인메모리 TTL 캐시."""

    def __init__(self, max_size=500):
        self._store = {}       # key → (value, expire_at)
        self._lock = threading.Lock()
        self._max_size = max_size

    def get(self, key):
        """캐시 조회. 만료/미존재 시 None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expire_at = entry
            if time.time() > expire_at:
                del self._store[key]
                return None
            return value

    def set(self, key, value, ttl=60):
        """캐시 저장. ttl: 초 단위 유효시간."""
        with self._lock:
            # 용량 초과 시 만료된 항목 정리
            if len(self._store) >= self._max_size:
                self._evict_expired()
            self._store[key] = (value, time.time() + ttl)

    def invalidate(self, prefix=None):
        """캐시 무효화. prefix 없으면 전체 삭제."""
        with self._lock:
            if prefix is None:
                self._store.clear()
            else:
                keys = [k for k in self._store if k.startswith(prefix)]
                for k in keys:
                    del self._store[k]

    def _evict_expired(self):
        """만료된 항목 제거 (lock 내에서 호출)."""
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]


# 싱글턴 인스턴스 — 대시보드 전용
dashboard_cache = TTLCache(max_size=200)


def invalidate_dashboard(operator_id=None, client_id=None):
    """주문/재고/과금 변경 시 관련 대시보드 캐시 무효화.

    호출 예시:
        from services.cache import invalidate_dashboard
        invalidate_dashboard(operator_id=1)          # 운영사 대시보드
        invalidate_dashboard(client_id=5)             # 고객 대시보드
        invalidate_dashboard(operator_id=1, client_id=5)  # 둘 다
    """
    if operator_id:
        dashboard_cache.invalidate(f'op_dash:{operator_id}')
    if client_id:
        dashboard_cache.invalidate(f'cl_dash:{client_id}')
    # operator_id/client_id 모두 없으면 전체 무효화
    if not operator_id and not client_id:
        dashboard_cache.invalidate()
