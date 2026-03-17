-- 013: 과금 중복방지(Idempotency) — dedupe_key 기반
-- Phase B 핵심: 동일 이벤트에 대한 이중 과금 방지

-- client_billing_logs에 dedupe_key 컬럼 추가
ALTER TABLE client_billing_logs ADD COLUMN IF NOT EXISTS dedupe_key TEXT;

-- client_id + dedupe_key 유니크 인덱스 (NULL은 무시)
CREATE UNIQUE INDEX IF NOT EXISTS uniq_billing_dedupe
    ON client_billing_logs (client_id, dedupe_key)
    WHERE dedupe_key IS NOT NULL;

-- failed_billing_events 상태 확장: retry 추가
-- (기존 pending/resolved/dismissed에 retry 상태 추가)
ALTER TABLE failed_billing_events
    DROP CONSTRAINT IF EXISTS failed_billing_events_status_check;

ALTER TABLE failed_billing_events
    ADD CONSTRAINT failed_billing_events_status_check
    CHECK (status IN ('pending', 'resolved', 'dismissed', 'retry'));
