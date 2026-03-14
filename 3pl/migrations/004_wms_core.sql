-- ═══════════════════════════════════════════
-- PackFlow WMS Core — Phase 1~3
-- 출고차단, 스캔검증, 피킹리스트, 재고예약
-- ═══════════════════════════════════════════

-- ── Phase 1: 주문 보류/차단 ──
ALTER TABLE orders ADD COLUMN IF NOT EXISTS hold_flag BOOLEAN DEFAULT FALSE;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS hold_reason TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS hold_by BIGINT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS hold_at TIMESTAMPTZ;

-- 주문 상태 변경 로그 (audit trail)
CREATE TABLE IF NOT EXISTS order_status_logs (
    id             BIGSERIAL PRIMARY KEY,
    operator_id    BIGINT NOT NULL,
    order_id       BIGINT NOT NULL REFERENCES orders(id),
    old_status     TEXT,
    new_status     TEXT NOT NULL,
    changed_by     BIGINT REFERENCES users(id),
    reason         TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_order_status_logs_order ON order_status_logs(order_id);
CREATE INDEX IF NOT EXISTS idx_order_status_logs_created ON order_status_logs(created_at);

-- ── Phase 2: 피킹리스트 ──
CREATE TABLE IF NOT EXISTS picking_lists (
    id             BIGSERIAL PRIMARY KEY,
    operator_id    BIGINT NOT NULL,
    list_no        TEXT NOT NULL,
    list_type      TEXT DEFAULT 'by_order',  -- by_order / by_product / by_location
    warehouse_id   BIGINT REFERENCES warehouses(id),
    client_id      BIGINT REFERENCES clients(id),
    status         TEXT DEFAULT 'created',   -- created / in_progress / completed
    assigned_to    BIGINT REFERENCES users(id),
    total_items    INT DEFAULT 0,
    picked_items   INT DEFAULT 0,
    created_by     BIGINT REFERENCES users(id),
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    completed_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_picking_lists_operator ON picking_lists(operator_id);
CREATE INDEX IF NOT EXISTS idx_picking_lists_status ON picking_lists(status);

CREATE TABLE IF NOT EXISTS picking_list_items (
    id               BIGSERIAL PRIMARY KEY,
    picking_list_id  BIGINT NOT NULL REFERENCES picking_lists(id) ON DELETE CASCADE,
    order_id         BIGINT REFERENCES orders(id),
    sku_id           BIGINT NOT NULL REFERENCES skus(id),
    location_id      BIGINT REFERENCES warehouse_locations(id),
    location_code    TEXT,
    expected_qty     INT NOT NULL,
    picked_qty       INT DEFAULT 0,
    lot_number       TEXT,
    status           TEXT DEFAULT 'pending',  -- pending / picked / short
    picked_at        TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_picking_items_list ON picking_list_items(picking_list_id);
CREATE INDEX IF NOT EXISTS idx_picking_items_sku ON picking_list_items(sku_id);

-- ── Phase 3: 재고 예약 ──
ALTER TABLE inventory_stock ADD COLUMN IF NOT EXISTS reserved_qty INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS inventory_reservations (
    id             BIGSERIAL PRIMARY KEY,
    operator_id    BIGINT NOT NULL,
    order_id       BIGINT NOT NULL REFERENCES orders(id),
    sku_id         BIGINT NOT NULL REFERENCES skus(id),
    location_id    BIGINT REFERENCES warehouse_locations(id),
    lot_number     TEXT,
    reserved_qty   INT NOT NULL,
    status         TEXT DEFAULT 'reserved',  -- reserved / committed / released
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    committed_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_reservations_order ON inventory_reservations(order_id);
CREATE INDEX IF NOT EXISTS idx_reservations_sku ON inventory_reservations(sku_id);
CREATE INDEX IF NOT EXISTS idx_reservations_status ON inventory_reservations(status);
