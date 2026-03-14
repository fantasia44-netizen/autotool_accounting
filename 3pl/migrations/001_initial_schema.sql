-- ═══════════════════════════════════════════
-- PackFlow 3PL SaaS — Initial Schema
-- Supabase (PostgreSQL)
-- ═══════════════════════════════════════════

-- ── 운영사 (3PL 회사) ──
CREATE TABLE operators (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    business_no TEXT,           -- 사업자등록번호
    ceo_name TEXT,
    phone TEXT,
    email TEXT,
    address TEXT,
    plan TEXT DEFAULT 'starter', -- starter/growth/enterprise
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 사용자 ──
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    operator_id BIGINT REFERENCES operators(id),
    client_id BIGINT,           -- FK added after clients table
    phone TEXT,
    email TEXT,
    is_approved BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 고객사 (화주) ──
CREATE TABLE clients (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    name TEXT NOT NULL,
    business_no TEXT,
    contact_name TEXT,
    contact_phone TEXT,
    contact_email TEXT,
    address TEXT,
    memo TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- users.client_id FK
ALTER TABLE users ADD CONSTRAINT fk_users_client
    FOREIGN KEY (client_id) REFERENCES clients(id);

-- ── 창고 ──
CREATE TABLE warehouses (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    name TEXT NOT NULL,
    address TEXT,
    storage_type TEXT DEFAULT 'ambient', -- ambient/cold/frozen
    memo TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 창고 구역 ──
CREATE TABLE warehouse_zones (
    id BIGSERIAL PRIMARY KEY,
    warehouse_id BIGINT NOT NULL REFERENCES warehouses(id),
    name TEXT NOT NULL,
    storage_temp TEXT DEFAULT 'ambient', -- ambient/cold/frozen
    memo TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 로케이션 ──
CREATE TABLE warehouse_locations (
    id BIGSERIAL PRIMARY KEY,
    zone_id BIGINT NOT NULL REFERENCES warehouse_zones(id),
    code TEXT NOT NULL,         -- e.g. A-01-01
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── SKU (상품) ──
CREATE TABLE skus (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    client_id BIGINT REFERENCES clients(id),
    sku_code TEXT NOT NULL,
    barcode TEXT,
    name TEXT NOT NULL,
    category TEXT,
    unit TEXT DEFAULT 'EA',
    storage_temp TEXT DEFAULT 'ambient',
    weight_g NUMERIC,
    memo TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(operator_id, sku_code)
);

-- ── 재고 (현재 수량) ──
CREATE TABLE inventory_stock (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    sku_id BIGINT NOT NULL REFERENCES skus(id),
    location_id BIGINT REFERENCES warehouse_locations(id),
    quantity INTEGER NOT NULL DEFAULT 0,
    lot_number TEXT,
    manufacture_date DATE,
    expiry_date DATE,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(sku_id, location_id, lot_number)
);

-- ── 재고 이동 이력 (수불장) ──
CREATE TABLE inventory_movements (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    sku_id BIGINT NOT NULL REFERENCES skus(id),
    location_id BIGINT REFERENCES warehouse_locations(id),
    movement_type TEXT NOT NULL, -- inbound/outbound/adjust/transfer_in/transfer_out
    quantity INTEGER NOT NULL,
    order_id BIGINT,
    lot_number TEXT,
    memo TEXT,
    user_id BIGINT REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 주문 ──
CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    client_id BIGINT REFERENCES clients(id),
    channel TEXT,               -- direct/coupang/naver/cafe24
    order_no TEXT,              -- 외부 주문번호
    status TEXT DEFAULT 'pending', -- pending/confirmed/packing/shipped/delivered/cancelled
    recipient_name TEXT,
    recipient_phone TEXT,
    recipient_address TEXT,
    memo TEXT,
    order_date TIMESTAMPTZ,
    shipped_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 주문 상세 ──
CREATE TABLE order_items (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    sku_id BIGINT NOT NULL REFERENCES skus(id),
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price NUMERIC DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 배송 ──
CREATE TABLE shipments (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    order_id BIGINT NOT NULL REFERENCES orders(id),
    courier TEXT,               -- cj/hanjin/lotte/logen
    invoice_no TEXT,
    status TEXT DEFAULT 'pending', -- pending/shipped/in_transit/delivered
    shipped_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 패킹 작업 ──
CREATE TABLE packing_jobs (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    user_id BIGINT REFERENCES users(id),
    order_id BIGINT REFERENCES orders(id),
    scanned_barcode TEXT,
    scanned_items JSONB DEFAULT '[]',
    status TEXT DEFAULT 'recording', -- recording/completed/cancelled
    video_path TEXT,
    video_size_bytes BIGINT,
    video_duration_ms INTEGER,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- ── 과금 요금제 ──
CREATE TABLE billing_plans (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,         -- starter/growth/enterprise
    price INTEGER NOT NULL,     -- 월 요금 (원)
    max_warehouses INTEGER DEFAULT 1,
    max_skus INTEGER DEFAULT 500,
    max_users INTEGER DEFAULT 5,
    has_video BOOLEAN DEFAULT FALSE,
    has_api BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 사용량 ──
CREATE TABLE billing_usage (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    year_month TEXT NOT NULL,   -- '2026-03'
    metric TEXT NOT NULL,       -- orders/shipments/storage_days
    count INTEGER DEFAULT 0,
    unit_price NUMERIC DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 청구서 ──
CREATE TABLE billing_invoices (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    year_month TEXT NOT NULL,
    total_amount NUMERIC DEFAULT 0,
    status TEXT DEFAULT 'pending', -- pending/paid/overdue
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ 인덱스 ═══

CREATE INDEX idx_users_operator ON users(operator_id);
CREATE INDEX idx_users_client ON users(client_id);
CREATE INDEX idx_clients_operator ON clients(operator_id);
CREATE INDEX idx_warehouses_operator ON warehouses(operator_id);
CREATE INDEX idx_skus_operator ON skus(operator_id);
CREATE INDEX idx_skus_client ON skus(client_id);
CREATE INDEX idx_inventory_stock_sku ON inventory_stock(sku_id);
CREATE INDEX idx_inventory_stock_operator ON inventory_stock(operator_id);
CREATE INDEX idx_inventory_movements_sku ON inventory_movements(sku_id);
CREATE INDEX idx_inventory_movements_operator ON inventory_movements(operator_id);
CREATE INDEX idx_inventory_movements_created ON inventory_movements(created_at);
CREATE INDEX idx_orders_operator ON orders(operator_id);
CREATE INDEX idx_orders_client ON orders(client_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_shipments_order ON shipments(order_id);
CREATE INDEX idx_shipments_operator ON shipments(operator_id);
CREATE INDEX idx_packing_jobs_operator ON packing_jobs(operator_id);
CREATE INDEX idx_packing_jobs_order ON packing_jobs(order_id);
CREATE INDEX idx_billing_usage_operator ON billing_usage(operator_id, year_month);
CREATE INDEX idx_billing_invoices_operator ON billing_invoices(operator_id);

-- ═══ 초기 데이터 ═══

-- 요금제
INSERT INTO billing_plans (name, price, max_warehouses, max_skus, max_users, has_video, has_api) VALUES
('starter', 49000, 1, 500, 5, FALSE, FALSE),
('growth', 149000, 5, -1, 20, TRUE, TRUE),
('enterprise', 0, -1, -1, -1, TRUE, TRUE);

-- ═══ 테스트 데이터 (TEST_MODE용) ═══
-- 아래는 테스트 환경에서만 실행. 상용 배포 시 실행하지 않음.
-- 별도 파일: 002_test_data.sql
