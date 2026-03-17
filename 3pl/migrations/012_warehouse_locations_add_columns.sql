-- 012: warehouse_locations 누락 컬럼 추가
ALTER TABLE warehouse_locations
    ADD COLUMN IF NOT EXISTS location_type TEXT DEFAULT 'shelf',
    ADD COLUMN IF NOT EXISTS memo TEXT;
