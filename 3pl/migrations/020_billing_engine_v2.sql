-- ============================================================
-- 020: 과금 엔진 v2.0 — 조건별 공식 기반 과금
-- Gemini + GPT 리뷰 반영 통합본
-- ============================================================

-- 1. client_rates 확장: 조건/공식/우선순위/이력관리
ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    conditions JSONB DEFAULT '{}';

ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    formula TEXT DEFAULT NULL;

ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    applies_to TEXT DEFAULT 'all';

ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    priority INT DEFAULT 100;

ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    is_stackable BOOLEAN DEFAULT TRUE;

ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    valid_from DATE DEFAULT '2020-01-01';

ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    valid_to DATE DEFAULT '2099-12-31';

ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    min_amount NUMERIC DEFAULT 0;

COMMENT ON COLUMN client_rates.conditions IS '적용 조건 JSONB: pack_type, weight범위, region, storage_temp 등';
COMMENT ON COLUMN client_rates.formula IS '계산 공식: {base_amount}+({item_count}-1)*100 등. NULL이면 amount×qty';
COMMENT ON COLUMN client_rates.applies_to IS 'all/single/multi/mixed — 포장형태 적용 대상';
COMMENT ON COLUMN client_rates.priority IS '우선순위 (낮을수록 우선, 기본=100)';
COMMENT ON COLUMN client_rates.is_stackable IS 'TRUE=다른 조건과 중첩 적용, FALSE=우선 적용 시 나머지 스킵';
COMMENT ON COLUMN client_rates.valid_from IS '요금 유효 시작일';
COMMENT ON COLUMN client_rates.valid_to IS '요금 유효 종료일';
COMMENT ON COLUMN client_rates.min_amount IS '수식 결과 최소 보장 금액 (음수 방지)';

-- 2. client_billing_logs 확장: 이벤트 기반 과금 + 공식 근거
ALTER TABLE client_billing_logs ADD COLUMN IF NOT EXISTS
    event_type TEXT DEFAULT NULL;

ALTER TABLE client_billing_logs ADD COLUMN IF NOT EXISTS
    event_status TEXT DEFAULT 'confirmed';

ALTER TABLE client_billing_logs ADD COLUMN IF NOT EXISTS
    formula_detail TEXT DEFAULT NULL;

ALTER TABLE client_billing_logs ADD COLUMN IF NOT EXISTS
    conditions_matched JSONB DEFAULT NULL;

COMMENT ON COLUMN client_billing_logs.event_type IS '과금 이벤트: inbound/outbound/storage/return/vas/material';
COMMENT ON COLUMN client_billing_logs.event_status IS 'created/confirmed/cancelled — 이벤트 상태';
COMMENT ON COLUMN client_billing_logs.formula_detail IS '적용된 공식과 변수값 기록 (감사추적)';
COMMENT ON COLUMN client_billing_logs.conditions_matched IS '매칭된 조건 기록';

-- 3. 보관비 일할 계산용 일별 재고 스냅샷
CREATE TABLE IF NOT EXISTS daily_inventory_snapshot (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    client_id BIGINT NOT NULL REFERENCES clients(id),
    snapshot_date DATE NOT NULL,
    storage_temp TEXT DEFAULT 'ambient',
    total_qty NUMERIC DEFAULT 0,
    pallet_count NUMERIC DEFAULT 0,
    cbm NUMERIC DEFAULT 0,
    sku_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_snap_unique
    ON daily_inventory_snapshot(operator_id, client_id, snapshot_date, storage_temp);

CREATE INDEX IF NOT EXISTS idx_daily_snap_date
    ON daily_inventory_snapshot(snapshot_date, client_id);

ALTER TABLE daily_inventory_snapshot ENABLE ROW LEVEL SECURITY;
CREATE POLICY daily_snap_tenant ON daily_inventory_snapshot
    USING (operator_id = current_setting('app.operator_id', true)::bigint);

-- 4. 요금 템플릿 (프리셋 재정의)
CREATE TABLE IF NOT EXISTS billing_rate_templates (
    id BIGSERIAL PRIMARY KEY,
    template_name TEXT NOT NULL,
    category TEXT NOT NULL,
    fee_name TEXT NOT NULL,
    fee_type TEXT DEFAULT 'fixed',
    default_amount NUMERIC DEFAULT 0,
    unit_label TEXT DEFAULT '건',
    conditions JSONB DEFAULT '{}',
    formula TEXT DEFAULT NULL,
    applies_to TEXT DEFAULT 'all',
    priority INT DEFAULT 100,
    is_stackable BOOLEAN DEFAULT TRUE,
    min_amount NUMERIC DEFAULT 0,
    description TEXT DEFAULT '',
    sort_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE
);

-- 기본 템플릿 데이터
INSERT INTO billing_rate_templates (template_name, category, fee_name, fee_type, default_amount, unit_label, conditions, formula, applies_to, priority, description, sort_order) VALUES
-- 출고비
('3PL 기본', 'outbound', '출고작업비(단품)', 'fixed', 300, '건', '{"pack_type":"single"}', '300', 'single', 100, '단품 출고 기본', 1),
('3PL 기본', 'outbound', '출고작업비(합포)', 'fixed', 300, '건', '{"pack_type":"multi"}', '{base_amount} + ({item_count} - 1) * 100', 'multi', 100, '합포장 기본+추가품목당', 2),
('3PL 기본', 'outbound', '출고작업비(이종합포)', 'fixed', 500, '건', '{"pack_type":"mixed"}', '500', 'mixed', 100, '이종합포장', 3),
-- 운송비
('3PL 기본', 'courier', '기본택배비', 'fixed', 3500, '건', '{}', '3500', 'all', 100, '기본 택배비', 10),
('3PL 기본', 'courier', '중량추가비', 'fixed', 500, 'kg', '{"weight_min_g":5001}', 'max(0, ceil({chargeable_weight_kg} - 5)) * 500', 'all', 110, '5kg 초과분', 11),
('3PL 기본', 'courier', '제주추가비', 'fixed', 3000, '건', '{"delivery_region":"제주"}', '3000', 'all', 120, '제주지역 추가', 12),
('3PL 기본', 'courier', '도서산간추가비', 'fixed', 5000, '건', '{"delivery_region":"도서"}', '5000', 'all', 120, '도서산간 추가', 13),
-- 입고비
('3PL 기본', 'inbound', '입고검수비', 'fixed', 50, '건', '{}', '{base_amount} * {qty}', 'all', 100, '건당 검수비', 20),
('3PL 기본', 'inbound', '파레트하차비', 'fixed', 5000, '파레트', '{}', '{base_amount} * {pallet_count}', 'all', 100, '파레트당', 21),
('3PL 기본', 'inbound', '상차비', 'fixed', 3000, '파레트', '{}', '{base_amount} * {pallet_count}', 'all', 100, '파레트당', 22),
-- 보관비 (일할)
('3PL 기본', 'storage', '일반보관비', 'fixed', 3000, '파레트/일', '{"storage_temp":"ambient"}', '{base_amount} * {pallet_count}', 'all', 100, '상온 일당', 30),
('3PL 기본', 'storage', '냉장보관비', 'fixed', 5000, '파레트/일', '{"storage_temp":"cold"}', '{base_amount} * {pallet_count}', 'all', 100, '냉장 일당', 31),
('3PL 기본', 'storage', '냉동보관비', 'fixed', 7000, '파레트/일', '{"storage_temp":"frozen"}', '{base_amount} * {pallet_count}', 'all', 100, '냉동 일당', 32),
-- 부자재비
('3PL 기본', 'material', '박스(소)', 'fixed', 500, '개', '{}', '{base_amount} * {qty}', 'all', 100, '', 40),
('3PL 기본', 'material', '박스(중)', 'fixed', 800, '개', '{}', '{base_amount} * {qty}', 'all', 100, '', 41),
('3PL 기본', 'material', '박스(대)', 'fixed', 1200, '개', '{}', '{base_amount} * {qty}', 'all', 100, '', 42),
('3PL 기본', 'material', '아이스팩', 'fixed', 300, '개', '{}', '{base_amount} * {qty}', 'all', 100, '', 43),
('3PL 기본', 'material', '완충재', 'fixed', 100, '개', '{}', '{base_amount} * {qty}', 'all', 100, '', 44),
-- 반품비
('3PL 기본', 'return', '반품수수료', 'fixed', 1000, '건', '{}', '1000', 'all', 100, '건당', 50),
('3PL 기본', 'return', '반품검수비', 'fixed', 500, '건', '{}', '{base_amount} * {qty}', 'all', 100, '수량당', 51),
('3PL 기본', 'return', '반품재포장비', 'fixed', 1500, '건', '{"cs_requires_repacking":true}', '1500 + {item_count} * 500', 'all', 100, '양품화 작업', 52)
ON CONFLICT DO NOTHING;
