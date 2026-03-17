-- ══════════════════════════════════════════════════════════════
-- 011: packing_jobs 추가 컬럼 (패킹 작업 상세 정보 저장)
-- 2026-03-17
-- ══════════════════════════════════════════════════════════════

ALTER TABLE packing_jobs ADD COLUMN IF NOT EXISTS channel TEXT DEFAULT '';
ALTER TABLE packing_jobs ADD COLUMN IF NOT EXISTS order_no TEXT DEFAULT '';
ALTER TABLE packing_jobs ADD COLUMN IF NOT EXISTS product_name TEXT DEFAULT '';
ALTER TABLE packing_jobs ADD COLUMN IF NOT EXISTS recipient_name TEXT DEFAULT '';
ALTER TABLE packing_jobs ADD COLUMN IF NOT EXISTS order_info JSONB DEFAULT '{}';
