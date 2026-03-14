-- 007: 3PL 과금 체계 강화 — 카테고리, 과금 로그, 정산서
-- client_rates에 카테고리 추가 + 과금 기록/정산서 테이블

ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'custom';
-- 카테고리: inbound, outbound, storage, courier, material, return, vas, custom

CREATE TABLE IF NOT EXISTS client_billing_logs (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL,
    client_id BIGINT NOT NULL,
    rate_id BIGINT,
    order_id BIGINT,
    year_month TEXT NOT NULL,
    fee_name TEXT NOT NULL,
    category TEXT DEFAULT 'custom',
    quantity NUMERIC(12,2) DEFAULT 1,
    unit_price NUMERIC(12,2) DEFAULT 0,
    total_amount NUMERIC(12,2) DEFAULT 0,
    memo TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_billing_logs_client_month
    ON client_billing_logs(client_id, year_month);
CREATE INDEX IF NOT EXISTS idx_billing_logs_category
    ON client_billing_logs(category);

CREATE TABLE IF NOT EXISTS client_invoices (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL,
    client_id BIGINT NOT NULL,
    year_month TEXT NOT NULL,
    total_amount NUMERIC(12,2) DEFAULT 0,
    status TEXT DEFAULT 'draft',
    confirmed_at TIMESTAMPTZ,
    memo TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(operator_id, client_id, year_month)
);
