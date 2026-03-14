-- 고객사별 요금표 (커스텀 항목, 최대 20개/고객사)
CREATE TABLE IF NOT EXISTS client_rates (
    id             BIGSERIAL PRIMARY KEY,
    operator_id    BIGINT NOT NULL,
    client_id      BIGINT NOT NULL REFERENCES clients(id),
    fee_name       TEXT NOT NULL,
    fee_type       TEXT NOT NULL DEFAULT 'fixed',   -- 'fixed' | 'rate'
    amount         NUMERIC(12,2) DEFAULT 0,          -- fixed=금액(원), rate=비율(%)
    unit_label     TEXT DEFAULT '건',
    sort_order     INT DEFAULT 0,
    is_active      BOOLEAN DEFAULT TRUE,
    effective_from DATE,
    memo           TEXT DEFAULT '',
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_client_rates_client ON client_rates(client_id);
CREATE INDEX IF NOT EXISTS idx_client_rates_operator ON client_rates(operator_id);
