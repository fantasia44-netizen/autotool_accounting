-- 015: shipments 테이블 확장 — 반품출고, 창고이동 지원
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS shipment_type TEXT DEFAULT 'normal';
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS client_id BIGINT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS sku_id BIGINT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS quantity INTEGER;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS reason TEXT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS from_warehouse_id BIGINT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS to_warehouse_id BIGINT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS location_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_shipments_type ON shipments(shipment_type);
CREATE INDEX IF NOT EXISTS idx_shipments_client ON shipments(client_id);
