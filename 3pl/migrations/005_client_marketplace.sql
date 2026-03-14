-- 005: 고객사별 마켓플레이스 API 인증정보
-- 화주사마다 스마트스토어/쿠팡/카페24 등의 API 키가 다름

CREATE TABLE IF NOT EXISTS client_marketplace_credentials (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL,
    client_id BIGINT NOT NULL REFERENCES clients(id),
    channel TEXT NOT NULL,              -- 'naver', 'coupang', 'cafe24'
    api_client_id TEXT,                 -- API 클라이언트 ID
    api_client_secret TEXT,             -- API 시크릿
    extra_config JSONB DEFAULT '{}',    -- 채널별 추가 필드 (vendor_id, mall_id 등)
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(operator_id, client_id, channel)
);

CREATE INDEX IF NOT EXISTS idx_client_mkt_client
    ON client_marketplace_credentials(client_id);
CREATE INDEX IF NOT EXISTS idx_client_mkt_operator
    ON client_marketplace_credentials(operator_id);
