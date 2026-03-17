-- 014: 감사 로그 (audit trail) + soft delete 확장 + 경영분석 테이블
-- 실행: Supabase SQL Editor에서 실행
-- ※ operators.id / users.id 가 BIGSERIAL이므로 FK도 BIGINT 사용

-- ═══════════════════════════════════════════
-- 1. 감사 로그 테이블 (모든 CUD 추적)
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT REFERENCES operators(id),
    user_id BIGINT REFERENCES users(id),
    user_name TEXT,
    action TEXT NOT NULL,          -- 'create', 'update', 'delete', 'restore'
    table_name TEXT NOT NULL,
    record_id TEXT,                -- 대상 레코드 ID
    before_data JSONB,            -- 변경 전 스냅샷 (update/delete 시)
    after_data JSONB,             -- 변경 후 스냅샷 (create/update 시)
    ip_address TEXT,
    memo TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_operator ON audit_logs(operator_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_table ON audit_logs(table_name, record_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at DESC);

-- ═══════════════════════════════════════════
-- 2. soft delete 컬럼 추가 (존재하는 테이블만)
-- ═══════════════════════════════════════════

-- orders
ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS deleted_by BIGINT;

-- shipments
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS deleted_by BIGINT;

-- packing_jobs
ALTER TABLE packing_jobs ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;
ALTER TABLE packing_jobs ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE packing_jobs ADD COLUMN IF NOT EXISTS deleted_by BIGINT;

-- client_billing_logs
ALTER TABLE client_billing_logs ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;
ALTER TABLE client_billing_logs ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE client_billing_logs ADD COLUMN IF NOT EXISTS deleted_by BIGINT;

-- client_invoices
ALTER TABLE client_invoices ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;
ALTER TABLE client_invoices ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE client_invoices ADD COLUMN IF NOT EXISTS deleted_by BIGINT;

-- picking_lists
ALTER TABLE picking_lists ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;
ALTER TABLE picking_lists ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE picking_lists ADD COLUMN IF NOT EXISTS deleted_by BIGINT;

-- 기존 soft delete 테이블에 deleted_by 추가
ALTER TABLE clients ADD COLUMN IF NOT EXISTS deleted_by BIGINT;
ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS deleted_by BIGINT;
ALTER TABLE skus ADD COLUMN IF NOT EXISTS deleted_by BIGINT;

-- ═══════════════════════════════════════════
-- 3. 아직 없는 테이블 생성 (입고, 재고조정)
-- ═══════════════════════════════════════════

CREATE TABLE IF NOT EXISTS inbound_receipts (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    client_id BIGINT REFERENCES clients(id),
    warehouse_id BIGINT REFERENCES warehouses(id),
    receipt_no TEXT,
    status TEXT DEFAULT 'pending',  -- pending/inspecting/completed/cancelled
    total_qty INTEGER DEFAULT 0,
    inspected_qty INTEGER DEFAULT 0,
    memo TEXT,
    received_by BIGINT REFERENCES users(id),
    received_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    deleted_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inbound_receipts_operator ON inbound_receipts(operator_id);
CREATE INDEX IF NOT EXISTS idx_inbound_receipts_client ON inbound_receipts(client_id);
CREATE INDEX IF NOT EXISTS idx_inbound_receipts_status ON inbound_receipts(status);

CREATE TABLE IF NOT EXISTS inventory_adjustments (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    sku_id BIGINT REFERENCES skus(id),
    location_id BIGINT REFERENCES warehouse_locations(id),
    adjust_type TEXT NOT NULL,    -- increase/decrease/write_off/correction
    quantity INTEGER NOT NULL,
    reason TEXT,
    memo TEXT,
    adjusted_by BIGINT REFERENCES users(id),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    deleted_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inventory_adj_operator ON inventory_adjustments(operator_id);
CREATE INDEX IF NOT EXISTS idx_inventory_adj_sku ON inventory_adjustments(sku_id);

-- ═══════════════════════════════════════════
-- 4. 경영분석 테이블
-- ═══════════════════════════════════════════

-- 비용 (세금계산서, 수동비용 등)
CREATE TABLE IF NOT EXISTS expenses (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    category TEXT NOT NULL,       -- 'tax_invoice', 'labor', 'rent', 'utility', 'supplies', 'etc'
    title TEXT NOT NULL,
    description TEXT,
    amount NUMERIC(15,2) NOT NULL DEFAULT 0,
    tax_amount NUMERIC(15,2) DEFAULT 0,
    vendor_name TEXT,             -- 거래처
    vendor_biz_no TEXT,           -- 사업자번호
    expense_date DATE NOT NULL,
    year_month TEXT NOT NULL,     -- 'YYYY-MM' 집계용
    receipt_url TEXT,             -- 영수증/세금계산서 파일 URL
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_expenses_operator ON expenses(operator_id);
CREATE INDEX IF NOT EXISTS idx_expenses_ym ON expenses(year_month);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);

-- 월별 경영 요약 (캐시 테이블, 재계산 가능)
CREATE TABLE IF NOT EXISTS monthly_pnl (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    year_month TEXT NOT NULL,     -- 'YYYY-MM'
    revenue NUMERIC(15,2) DEFAULT 0,       -- 매출 (고객 청구 합계)
    cost_of_service NUMERIC(15,2) DEFAULT 0, -- 원가 (인건비+부자재 등)
    operating_expense NUMERIC(15,2) DEFAULT 0, -- 판관비
    gross_profit NUMERIC(15,2) DEFAULT 0,  -- 매출총이익
    net_income NUMERIC(15,2) DEFAULT 0,    -- 순이익
    detail JSONB,                          -- 카테고리별 상세 breakdown
    calculated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(operator_id, year_month)
);

CREATE INDEX IF NOT EXISTS idx_monthly_pnl_operator ON monthly_pnl(operator_id);
