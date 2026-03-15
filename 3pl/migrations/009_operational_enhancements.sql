-- 009: 운영 기능 강화 — 재고알림, 보관비 고도화, 고객포털 과금
-- 2026-03-15

-- 1. SKU에 최소재고 설정 (고객사별 알림 기준)
ALTER TABLE skus ADD COLUMN IF NOT EXISTS min_stock_qty INTEGER DEFAULT 0;
ALTER TABLE skus ADD COLUMN IF NOT EXISTS max_stock_qty INTEGER DEFAULT 0;

-- 2. inventory_stock에 storage_temp (보관비 온도구간 연동)
-- storage_temp는 SKU 테이블에 이미 있음 (ambient/cold/frozen)
-- 보관비 계산 시 SKU의 storage_temp와 rate의 fee_name을 매칭

-- 3. client_rates에 storage_unit 추가 (보관비 단위: per_item, per_pallet, per_cbm, per_location)
ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS storage_unit TEXT DEFAULT 'per_item';
-- storage_unit: per_item(개당), per_pallet(팔레트당), per_cbm(CBM당), per_location(로케이션당)

-- 4. 일별 재고 스냅샷 (보관비 정확 계산용)
CREATE TABLE IF NOT EXISTS daily_inventory_snapshot (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL,
    client_id BIGINT NOT NULL,
    sku_id BIGINT NOT NULL,
    snapshot_date DATE NOT NULL,
    quantity NUMERIC(12,2) DEFAULT 0,
    storage_temp TEXT DEFAULT 'ambient',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(operator_id, client_id, sku_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_snapshot_client_date
    ON daily_inventory_snapshot(client_id, snapshot_date);
