-- 017: API Keys 테이블 — 외부 REST API 인증용
-- 2026-03-18

CREATE TABLE IF NOT EXISTS api_keys (
    id          BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES users(id),
    client_id   BIGINT REFERENCES clients(id),
    name        TEXT NOT NULL DEFAULT 'Default',         -- 키 이름 (사용자 구분용)
    api_key     TEXT,                                    -- 평문 키 (마이그레이션 호환)
    key_hash    TEXT NOT NULL,                           -- SHA-256 해시
    is_active   BOOLEAN NOT NULL DEFAULT true,
    last_used_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ,                             -- NULL = 무기한
    UNIQUE (key_hash)
);

-- RLS 정책
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

CREATE POLICY api_keys_tenant ON api_keys
    USING (operator_id = current_setting('app.current_operator_id', true)::BIGINT);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys (key_hash) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_api_keys_operator ON api_keys (operator_id);

COMMENT ON TABLE api_keys IS '외부 REST API 인증용 키 관리';
