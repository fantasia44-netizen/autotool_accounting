"""패킹 작업 Repository."""
from .base import BaseRepository


class PackingRepository(BaseRepository):
    """패킹 작업 CRUD + 실적 조회 + 영상 관리."""

    TABLE = 'packing_jobs'
    STORAGE_BUCKET = 'packing-videos'

    def list_jobs(self, status=None, user_id=None, limit=100):
        filters = []
        if status:
            filters.append(('status', 'eq', status))
        if user_id:
            filters.append(('user_id', 'eq', user_id))
        return self._query(self.TABLE, filters=filters or None,
                           order_by='started_at', limit=limit)

    def get_job(self, job_id):
        rows = self._query(self.TABLE, filters=[('id', 'eq', job_id)])
        return rows[0] if rows else None

    def create_job(self, data):
        return self._insert(self.TABLE, data)

    def update_job(self, job_id, data):
        return self._update(self.TABLE, job_id, data)

    def complete_job(self, job_id, video_path=None, video_size=None, video_duration=None):
        payload = {'status': 'completed', 'completed_at': 'now()'}
        if video_path:
            payload['video_path'] = video_path
        if video_size:
            payload['video_size_bytes'] = video_size
        if video_duration:
            payload['video_duration_ms'] = video_duration
        return self._update(self.TABLE, job_id, payload)

    def get_pending_queue(self):
        """패킹 대기 큐 — recording 상태 작업 목록."""
        return self._query(self.TABLE,
                           filters=[('status', 'eq', 'recording')],
                           order_by='started_at', order_desc=False)

    def get_worker_stats(self, user_id, year_month=None):
        """작업자 실적 — 완료 건수."""
        filters = [('user_id', 'eq', user_id), ('status', 'eq', 'completed')]
        return self._query(self.TABLE, filters=filters,
                           order_by='completed_at')

    def list_by_order(self, order_id):
        return self._query(self.TABLE,
                           filters=[('order_id', 'eq', order_id)],
                           order_by='started_at')

    # ── 영상 관리 ──

    def upload_video(self, path, video_bytes):
        """Supabase Storage에 영상 업로드."""
        if not self.client:
            return None
        return self.client.storage.from_(self.STORAGE_BUCKET).upload(
            path, video_bytes, {'content-type': 'video/webm'}
        )

    def get_video_url(self, video_path, expires_in=3600):
        """Supabase Storage signed URL 생성."""
        if not self.client or not video_path:
            return None
        try:
            res = self.client.storage.from_(self.STORAGE_BUCKET).create_signed_url(
                video_path, expires_in
            )
            return res.get('signedURL') or res.get('signedUrl')
        except Exception:
            return None
