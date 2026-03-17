-- 010: Soft Delete 컬럼 + 보안 인덱스 추가
-- 2026-03-17

-- ═══ soft delete 컬럼 추가 ═══

ALTER TABLE client_rates
    ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

ALTER TABLE client_marketplace_credentials
    ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

ALTER TABLE skus
    ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

-- ═══ soft delete 인덱스 (미삭제 레코드 빠른 조회) ═══

CREATE INDEX IF NOT EXISTS idx_client_rates_not_deleted
    ON client_rates (is_deleted) WHERE is_deleted = FALSE OR is_deleted IS NULL;

CREATE INDEX IF NOT EXISTS idx_client_mkt_creds_not_deleted
    ON client_marketplace_credentials (is_deleted) WHERE is_deleted = FALSE OR is_deleted IS NULL;

CREATE INDEX IF NOT EXISTS idx_clients_not_deleted
    ON clients (is_deleted) WHERE is_deleted = FALSE OR is_deleted IS NULL;

CREATE INDEX IF NOT EXISTS idx_skus_not_deleted
    ON skus (is_deleted) WHERE is_deleted = FALSE OR is_deleted IS NULL;
