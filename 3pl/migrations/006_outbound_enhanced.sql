-- 006: 출고관리 강화 — 반품출고, 창고이동 지원
-- shipments 테이블에 유형/사유/창고 정보 추가

ALTER TABLE shipments ADD COLUMN IF NOT EXISTS shipment_type TEXT DEFAULT 'normal';
-- 'normal' (일반출고), 'return' (반품출고), 'transfer' (창고이동)

ALTER TABLE shipments ADD COLUMN IF NOT EXISTS client_id BIGINT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS from_warehouse_id BIGINT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS to_warehouse_id BIGINT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS reason TEXT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS sku_id BIGINT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS quantity INT;

CREATE INDEX IF NOT EXISTS idx_shipments_type
    ON shipments(shipment_type);
CREATE INDEX IF NOT EXISTS idx_shipments_client
    ON shipments(client_id);

-- CHECK 제약: 데이터 무결성 보호
-- shipment_type 값 제한
ALTER TABLE shipments DROP CONSTRAINT IF EXISTS chk_shipment_type;
ALTER TABLE shipments ADD CONSTRAINT chk_shipment_type
    CHECK (shipment_type IN ('normal', 'return', 'transfer'));

-- 창고이동 시 출발/도착 창고 필수
ALTER TABLE shipments DROP CONSTRAINT IF EXISTS chk_transfer_warehouses;
ALTER TABLE shipments ADD CONSTRAINT chk_transfer_warehouses
    CHECK (shipment_type != 'transfer'
           OR (from_warehouse_id IS NOT NULL AND to_warehouse_id IS NOT NULL));

-- 반품출고 시 고객사 필수
ALTER TABLE shipments DROP CONSTRAINT IF EXISTS chk_return_client;
ALTER TABLE shipments ADD CONSTRAINT chk_return_client
    CHECK (shipment_type != 'return' OR client_id IS NOT NULL);

-- 창고이동: 출발/도착 창고 다름 보장
ALTER TABLE shipments DROP CONSTRAINT IF EXISTS chk_transfer_diff_warehouse;
ALTER TABLE shipments ADD CONSTRAINT chk_transfer_diff_warehouse
    CHECK (shipment_type != 'transfer'
           OR from_warehouse_id != to_warehouse_id);
