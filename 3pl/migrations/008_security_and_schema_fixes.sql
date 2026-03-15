-- 008: 보안/스키마 보강 (GPT+Gemini+Claude 리뷰 반영)
-- 2026-03-15

-- ═══ 1. FK 제약 복원 (007 누락분) ═══

ALTER TABLE client_billing_logs
    ADD CONSTRAINT fk_billing_logs_operator FOREIGN KEY (operator_id) REFERENCES operators(id),
    ADD CONSTRAINT fk_billing_logs_client   FOREIGN KEY (client_id)   REFERENCES clients(id),
    ADD CONSTRAINT fk_billing_logs_rate     FOREIGN KEY (rate_id)     REFERENCES client_rates(id),
    ADD CONSTRAINT fk_billing_logs_order    FOREIGN KEY (order_id)    REFERENCES orders(id);

ALTER TABLE client_invoices
    ADD CONSTRAINT fk_invoices_operator FOREIGN KEY (operator_id) REFERENCES operators(id),
    ADD CONSTRAINT fk_invoices_client   FOREIGN KEY (client_id)   REFERENCES clients(id);

ALTER TABLE client_rates
    ADD CONSTRAINT fk_rates_operator FOREIGN KEY (operator_id) REFERENCES operators(id),
    ADD CONSTRAINT fk_rates_client   FOREIGN KEY (client_id)   REFERENCES clients(id);

-- 006 shipments 확장 컬럼 FK
ALTER TABLE shipments
    ADD CONSTRAINT fk_shipments_client       FOREIGN KEY (client_id)         REFERENCES clients(id),
    ADD CONSTRAINT fk_shipments_from_wh      FOREIGN KEY (from_warehouse_id) REFERENCES warehouses(id),
    ADD CONSTRAINT fk_shipments_to_wh        FOREIGN KEY (to_warehouse_id)   REFERENCES warehouses(id),
    ADD CONSTRAINT fk_shipments_sku          FOREIGN KEY (sku_id)            REFERENCES skus(id);


-- ═══ 2. 과금 실패 이벤트 테이블 (DLQ 역할) ═══

CREATE TABLE IF NOT EXISTS failed_billing_events (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    client_id BIGINT NOT NULL REFERENCES clients(id),
    event_type TEXT NOT NULL,       -- inbound_fee, outbound_fee, return_fee, packing_fee
    event_data JSONB NOT NULL,      -- 원본 과금 파라미터
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',  -- pending / resolved / abandoned
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_failed_billing_status
    ON failed_billing_events(status) WHERE status = 'pending';


-- ═══ 3. year_month TEXT → DATE 변환 ═══

-- client_billing_logs
ALTER TABLE client_billing_logs
    ADD COLUMN IF NOT EXISTS billing_date DATE;

UPDATE client_billing_logs
    SET billing_date = (year_month || '-01')::DATE
    WHERE billing_date IS NULL AND year_month IS NOT NULL;

-- client_invoices
ALTER TABLE client_invoices
    ADD COLUMN IF NOT EXISTS billing_date DATE;

UPDATE client_invoices
    SET billing_date = (year_month || '-01')::DATE
    WHERE billing_date IS NULL AND year_month IS NOT NULL;

-- billing_usage
ALTER TABLE billing_usage
    ADD COLUMN IF NOT EXISTS billing_date DATE;

UPDATE billing_usage
    SET billing_date = (year_month || '-01')::DATE
    WHERE billing_date IS NULL AND year_month IS NOT NULL;

-- billing_invoices
ALTER TABLE billing_invoices
    ADD COLUMN IF NOT EXISTS billing_date DATE;

UPDATE billing_invoices
    SET billing_date = (year_month || '-01')::DATE
    WHERE billing_date IS NULL AND year_month IS NOT NULL;

-- 기존 TEXT 컬럼은 유지 (하위호환), 새 코드에서 billing_date 사용
-- 이후 안정화되면 year_month DROP 가능


-- ═══ 4. client_invoices 리비전 관리 ═══

-- UNIQUE 제약 제거 후 revision_no 추가
ALTER TABLE client_invoices
    DROP CONSTRAINT IF EXISTS client_invoices_operator_id_client_id_year_month_key;

ALTER TABLE client_invoices
    ADD COLUMN IF NOT EXISTS revision_no INTEGER DEFAULT 1,
    ADD COLUMN IF NOT EXISTS parent_invoice_id BIGINT REFERENCES client_invoices(id),
    ADD COLUMN IF NOT EXISTS voided_at TIMESTAMPTZ;

-- status 확장: draft / confirmed / sent / paid / amended / voided
-- 새 UNIQUE: operator_id + client_id + year_month + revision_no
ALTER TABLE client_invoices
    ADD CONSTRAINT uq_invoices_revision
    UNIQUE(operator_id, client_id, year_month, revision_no);

COMMENT ON COLUMN client_invoices.revision_no IS '정산서 리비전 번호 (1=원본, 2+=수정분)';
COMMENT ON COLUMN client_invoices.parent_invoice_id IS '수정 전 원본 정산서 ID';
COMMENT ON COLUMN client_invoices.voided_at IS '무효화 일시';
