-- ============================================================
-- 018: PackFlow 듀얼모드 기반 (Speed / Precision)
-- ============================================================

-- 1. clients 테이블: 풀필먼트 모드 추가
ALTER TABLE clients ADD COLUMN IF NOT EXISTS fulfillment_mode TEXT DEFAULT 'precision';
COMMENT ON COLUMN clients.fulfillment_mode IS 'speed: 속도모드(저가대량) / precision: 안정모드(고가검수)';

-- 2. skus 테이블: SKU별 모드 오버라이드
ALTER TABLE skus ADD COLUMN IF NOT EXISTS fulfillment_mode_override TEXT DEFAULT NULL;
COMMENT ON COLUMN skus.fulfillment_mode_override IS 'NULL=고객사모드 따름, speed/precision=SKU별 오버라이드';

-- 3. orders 테이블: 주문별 확정된 모드 + 단품/합포 구분
ALTER TABLE orders ADD COLUMN IF NOT EXISTS fulfillment_mode TEXT DEFAULT NULL;
COMMENT ON COLUMN orders.fulfillment_mode IS '주문 확정 시 결정된 모드 (speed/precision)';

ALTER TABLE orders ADD COLUMN IF NOT EXISTS pack_type TEXT DEFAULT NULL;
COMMENT ON COLUMN orders.pack_type IS 'single: 단품 / multi: 합포 (속도모드 피킹 분류용)';

-- 4. 과금 비동기 큐
CREATE TABLE IF NOT EXISTS billing_queue (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    client_id BIGINT NOT NULL REFERENCES clients(id),
    event_type TEXT NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_billing_queue_status
    ON billing_queue(status, created_at);
CREATE INDEX IF NOT EXISTS idx_billing_queue_client
    ON billing_queue(client_id, status);

ALTER TABLE billing_queue ENABLE ROW LEVEL SECURITY;
CREATE POLICY billing_queue_tenant ON billing_queue
    USING (operator_id = current_setting('app.operator_id', true)::bigint);

-- 5. 작업자 활동 로그 (KPI 트래킹)
CREATE TABLE IF NOT EXISTS worker_activity_log (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    user_id BIGINT NOT NULL REFERENCES users(id),
    activity_type TEXT NOT NULL,
    fulfillment_mode TEXT NOT NULL DEFAULT 'precision',
    order_id BIGINT,
    item_count INT DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_worker_activity_user
    ON worker_activity_log(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_worker_activity_mode
    ON worker_activity_log(fulfillment_mode, created_at);

ALTER TABLE worker_activity_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY worker_activity_tenant ON worker_activity_log
    USING (operator_id = current_setting('app.operator_id', true)::bigint);
