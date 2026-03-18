-- ============================================================================
-- 016: 동시접속 환경 재고 레이스컨디션 방지용 RPC 함수
-- 목적: 원자적(atomic) 재고 연산을 PL/pgSQL 함수로 제공하여
--       동시 요청 시 데이터 정합성을 보장한다.
-- 대상 테이블: inventory_stock, inventory_movements, inventory_reservations,
--              client_billing_logs
-- ============================================================================

-- ─────────────────────────────────────────────
-- 1. fn_adjust_stock
--    재고 수량을 원자적으로 증감한다.
--    레코드 없으면 INSERT(delta>0), 재고 부족이면 에러.
-- ─────────────────────────────────────────────
DROP FUNCTION IF EXISTS fn_adjust_stock(BIGINT, BIGINT, BIGINT, INTEGER, TEXT, TEXT, BIGINT);

CREATE OR REPLACE FUNCTION fn_adjust_stock(
    p_operator_id  BIGINT,
    p_sku_id       BIGINT,
    p_location_id  BIGINT,
    p_delta        INTEGER,
    p_lot_number   TEXT DEFAULT NULL,
    p_memo         TEXT DEFAULT NULL,
    p_user_id      BIGINT DEFAULT NULL
) RETURNS JSON
LANGUAGE plpgsql
AS $$
DECLARE
    v_stock        RECORD;
    v_new_qty      INTEGER;
    v_stock_id     BIGINT;
BEGIN
    -- 기존 재고 레코드 조회 (FOR UPDATE 잠금)
    SELECT id, quantity
      INTO v_stock
      FROM inventory_stock
     WHERE operator_id  = p_operator_id
       AND sku_id       = p_sku_id
       AND location_id IS NOT DISTINCT FROM p_location_id
       AND lot_number  IS NOT DISTINCT FROM p_lot_number
     FOR UPDATE;

    IF v_stock IS NULL THEN
        -- 레코드 없음: delta > 0 일 때만 신규 생성
        IF p_delta <= 0 THEN
            RETURN json_build_object(
                'ok',    FALSE,
                'error', format('재고 레코드 없음 (sku_id=%s, location_id=%s). 차감 불가.', p_sku_id, p_location_id)
            );
        END IF;

        INSERT INTO inventory_stock (operator_id, sku_id, location_id, quantity, lot_number, updated_at)
        VALUES (p_operator_id, p_sku_id, p_location_id, p_delta, p_lot_number, NOW())
        RETURNING id, quantity INTO v_stock_id, v_new_qty;
    ELSE
        -- 기존 레코드 존재: 재고 부족 체크
        v_new_qty := v_stock.quantity + p_delta;
        IF v_new_qty < 0 THEN
            RAISE EXCEPTION '재고 부족: sku_id=%, location_id=%, 현재=%,  요청delta=%, 결과=%',
                p_sku_id, p_location_id, v_stock.quantity, p_delta, v_new_qty;
        END IF;

        UPDATE inventory_stock
           SET quantity   = v_new_qty,
               updated_at = NOW()
         WHERE id = v_stock.id;

        v_stock_id := v_stock.id;
    END IF;

    -- 이력 기록
    INSERT INTO inventory_movements
        (operator_id, sku_id, location_id, movement_type, quantity, lot_number, memo, user_id, created_at)
    VALUES
        (p_operator_id, p_sku_id, p_location_id, 'adjust', p_delta, p_lot_number, p_memo, p_user_id, NOW());

    RETURN json_build_object(
        'ok',           TRUE,
        'stock_id',     v_stock_id,
        'new_quantity', v_new_qty
    );
END;
$$;


-- ─────────────────────────────────────────────
-- 2. fn_transfer_stock
--    하나의 트랜잭션으로 출발지 차감 + 도착지 증가.
--    출발지 재고 부족 시 에러.
-- ─────────────────────────────────────────────
DROP FUNCTION IF EXISTS fn_transfer_stock(BIGINT, BIGINT, BIGINT, BIGINT, INTEGER, TEXT, TEXT, BIGINT);

CREATE OR REPLACE FUNCTION fn_transfer_stock(
    p_operator_id      BIGINT,
    p_sku_id           BIGINT,
    p_from_location_id BIGINT,
    p_to_location_id   BIGINT,
    p_quantity         INTEGER,
    p_lot_number       TEXT DEFAULT NULL,
    p_memo             TEXT DEFAULT NULL,
    p_user_id          BIGINT DEFAULT NULL
) RETURNS JSON
LANGUAGE plpgsql
AS $$
DECLARE
    v_from       RECORD;
    v_to         RECORD;
    v_from_qty   INTEGER;
    v_to_qty     INTEGER;
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION '이동 수량은 양수여야 합니다: %', p_quantity;
    END IF;

    -- 출발지 잠금 & 차감
    SELECT id, quantity
      INTO v_from
      FROM inventory_stock
     WHERE operator_id  = p_operator_id
       AND sku_id       = p_sku_id
       AND location_id IS NOT DISTINCT FROM p_from_location_id
       AND lot_number  IS NOT DISTINCT FROM p_lot_number
     FOR UPDATE;

    IF v_from IS NULL OR v_from.quantity < p_quantity THEN
        RAISE EXCEPTION '출발지 재고 부족: sku_id=%, from_location=%, 현재=%, 요청=%',
            p_sku_id, p_from_location_id, COALESCE(v_from.quantity, 0), p_quantity;
    END IF;

    v_from_qty := v_from.quantity - p_quantity;
    UPDATE inventory_stock
       SET quantity   = v_from_qty,
           updated_at = NOW()
     WHERE id = v_from.id;

    -- 도착지 잠금 & 증가 (없으면 생성)
    SELECT id, quantity
      INTO v_to
      FROM inventory_stock
     WHERE operator_id  = p_operator_id
       AND sku_id       = p_sku_id
       AND location_id IS NOT DISTINCT FROM p_to_location_id
       AND lot_number  IS NOT DISTINCT FROM p_lot_number
     FOR UPDATE;

    IF v_to IS NULL THEN
        INSERT INTO inventory_stock (operator_id, sku_id, location_id, quantity, lot_number, updated_at)
        VALUES (p_operator_id, p_sku_id, p_to_location_id, p_quantity, p_lot_number, NOW())
        RETURNING quantity INTO v_to_qty;
    ELSE
        v_to_qty := v_to.quantity + p_quantity;
        UPDATE inventory_stock
           SET quantity   = v_to_qty,
               updated_at = NOW()
         WHERE id = v_to.id;
    END IF;

    -- 이력: transfer_out + transfer_in
    INSERT INTO inventory_movements
        (operator_id, sku_id, location_id, movement_type, quantity, lot_number, memo, user_id, created_at)
    VALUES
        (p_operator_id, p_sku_id, p_from_location_id, 'transfer_out', -p_quantity, p_lot_number, p_memo, p_user_id, NOW()),
        (p_operator_id, p_sku_id, p_to_location_id,   'transfer_in',   p_quantity, p_lot_number, p_memo, p_user_id, NOW());

    RETURN json_build_object(
        'ok',       TRUE,
        'from_qty', v_from_qty,
        'to_qty',   v_to_qty
    );
END;
$$;


-- ─────────────────────────────────────────────
-- 3. fn_reserve_stock
--    주문에 대해 SKU별 FIFO(expiry_date ASC) 예약.
--    하나라도 부족하면 전체 ROLLBACK.
-- ─────────────────────────────────────────────
DROP FUNCTION IF EXISTS fn_reserve_stock(BIGINT, BIGINT, JSON);

CREATE OR REPLACE FUNCTION fn_reserve_stock(
    p_operator_id  BIGINT,
    p_order_id     BIGINT,
    p_items        JSON
) RETURNS JSON
LANGUAGE plpgsql
AS $$
DECLARE
    v_item         JSON;
    v_sku_id       BIGINT;
    v_need_qty     INTEGER;
    v_remain       INTEGER;
    v_stock_row    RECORD;
    v_alloc        INTEGER;
    v_reservations JSON[] := '{}';
    v_res_id       BIGINT;
BEGIN
    -- 각 SKU 순회
    FOR v_item IN SELECT * FROM json_array_elements(p_items)
    LOOP
        v_sku_id   := (v_item ->> 'sku_id')::BIGINT;
        v_need_qty := (v_item ->> 'quantity')::INTEGER;
        v_remain   := v_need_qty;

        IF v_need_qty <= 0 THEN
            RAISE EXCEPTION '예약 수량은 양수여야 합니다: sku_id=%, qty=%', v_sku_id, v_need_qty;
        END IF;

        -- FIFO: expiry_date ASC, 잠금
        FOR v_stock_row IN
            SELECT id, quantity, reserved_qty, location_id, lot_number, expiry_date
              FROM inventory_stock
             WHERE operator_id = p_operator_id
               AND sku_id     = v_sku_id
               AND (quantity - reserved_qty) > 0
             ORDER BY expiry_date ASC NULLS LAST, id ASC
             FOR UPDATE
        LOOP
            EXIT WHEN v_remain <= 0;

            v_alloc := LEAST(v_remain, v_stock_row.quantity - v_stock_row.reserved_qty);

            UPDATE inventory_stock
               SET reserved_qty = reserved_qty + v_alloc,
                   updated_at   = NOW()
             WHERE id = v_stock_row.id;

            INSERT INTO inventory_reservations
                (operator_id, order_id, sku_id, location_id, lot_number, reserved_qty, status, created_at)
            VALUES
                (p_operator_id, p_order_id, v_sku_id, v_stock_row.location_id,
                 v_stock_row.lot_number, v_alloc, 'reserved', NOW())
            RETURNING id INTO v_res_id;

            v_reservations := array_append(v_reservations, json_build_object(
                'reservation_id', v_res_id,
                'sku_id',         v_sku_id,
                'location_id',    v_stock_row.location_id,
                'lot_number',     v_stock_row.lot_number,
                'reserved_qty',   v_alloc
            ));

            v_remain := v_remain - v_alloc;
        END LOOP;

        -- 재고 부족 → 전체 ROLLBACK (트랜잭션 내부이므로 RAISE로 자동 롤백)
        IF v_remain > 0 THEN
            RAISE EXCEPTION '__STOCK_SHORT__|sku_id=%,short=%',
                v_sku_id, v_remain;
        END IF;
    END LOOP;

    RETURN json_build_object(
        'ok',           TRUE,
        'reservations', array_to_json(v_reservations)
    );

EXCEPTION
    WHEN OTHERS THEN
        -- __STOCK_SHORT__ 패턴이면 구조화된 에러 반환
        IF SQLERRM LIKE '__STOCK_SHORT__%' THEN
            RETURN json_build_object(
                'ok',           FALSE,
                'error',        '재고 부족으로 예약 실패',
                'short_sku_id', (regexp_match(SQLERRM, 'sku_id=(\d+)'))[1]::BIGINT
            );
        END IF;
        RAISE;  -- 그 외 에러는 그대로 전파
END;
$$;


-- ─────────────────────────────────────────────
-- 4. fn_commit_stock
--    예약 확정: reserved → committed.
--    멱등성 보장 (이미 committed면 무시).
-- ─────────────────────────────────────────────
DROP FUNCTION IF EXISTS fn_commit_stock(BIGINT, BIGINT);

CREATE OR REPLACE FUNCTION fn_commit_stock(
    p_operator_id  BIGINT,
    p_order_id     BIGINT
) RETURNS JSON
LANGUAGE plpgsql
AS $$
DECLARE
    v_res          RECORD;
    v_committed    INTEGER := 0;
BEGIN
    -- 해당 주문의 reserved 예약건 순회 (FOR UPDATE 잠금)
    FOR v_res IN
        SELECT r.id, r.sku_id, r.location_id, r.lot_number, r.reserved_qty
          FROM inventory_reservations r
         WHERE r.operator_id = p_operator_id
           AND r.order_id    = p_order_id
           AND r.status      = 'reserved'
         FOR UPDATE
    LOOP
        -- inventory_stock: quantity 차감, reserved_qty 차감 (원자적)
        UPDATE inventory_stock
           SET quantity     = quantity     - v_res.reserved_qty,
               reserved_qty = reserved_qty - v_res.reserved_qty,
               updated_at   = NOW()
         WHERE operator_id  = p_operator_id
           AND sku_id       = v_res.sku_id
           AND location_id IS NOT DISTINCT FROM v_res.location_id
           AND lot_number  IS NOT DISTINCT FROM v_res.lot_number;

        -- 출고 이력
        INSERT INTO inventory_movements
            (operator_id, sku_id, location_id, movement_type, quantity, order_id, lot_number, memo, created_at)
        VALUES
            (p_operator_id, v_res.sku_id, v_res.location_id, 'outbound',
             -v_res.reserved_qty, p_order_id, v_res.lot_number, '예약 확정 출고', NOW());

        -- 예약 상태 변경
        UPDATE inventory_reservations
           SET status       = 'committed',
               committed_at = NOW()
         WHERE id = v_res.id;

        v_committed := v_committed + 1;
    END LOOP;

    -- 멱등성: 예약건이 없어도 에러 아님
    IF v_committed = 0 THEN
        RETURN json_build_object(
            'ok',      TRUE,
            'message', '이미 처리됨'
        );
    END IF;

    RETURN json_build_object(
        'ok',              TRUE,
        'committed_count', v_committed
    );
END;
$$;


-- ─────────────────────────────────────────────
-- 5. fn_log_fee_safe
--    과금 로그를 중복 없이 안전하게 기록.
--    dedupe_key 존재 시 기존 row 반환 (멱등).
-- ─────────────────────────────────────────────
DROP FUNCTION IF EXISTS fn_log_fee_safe(BIGINT, JSON, TEXT);

CREATE OR REPLACE FUNCTION fn_log_fee_safe(
    p_operator_id  BIGINT,
    p_data         JSON,
    p_dedupe_key   TEXT DEFAULT NULL
) RETURNS JSON
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing     RECORD;
    v_new_id       BIGINT;
BEGIN
    -- dedupe_key가 있으면 중복 확인
    IF p_dedupe_key IS NOT NULL THEN
        SELECT id INTO v_existing
          FROM client_billing_logs
         WHERE operator_id = p_operator_id
           AND dedupe_key  = p_dedupe_key;

        IF v_existing IS NOT NULL THEN
            RETURN json_build_object(
                'ok',           TRUE,
                'id',           v_existing.id,
                'is_duplicate', TRUE
            );
        END IF;
    END IF;

    INSERT INTO client_billing_logs
        (operator_id, client_id, rate_id, order_id, year_month,
         fee_name, category, quantity, unit_price, total_amount,
         memo, dedupe_key, created_at)
    VALUES
        (p_operator_id,
         (p_data ->> 'client_id')::BIGINT,
         (p_data ->> 'rate_id')::BIGINT,
         (p_data ->> 'order_id')::BIGINT,
         p_data ->> 'year_month',
         p_data ->> 'fee_name',
         COALESCE(p_data ->> 'category', 'custom'),
         COALESCE((p_data ->> 'quantity')::NUMERIC, 1),
         COALESCE((p_data ->> 'unit_price')::NUMERIC, 0),
         COALESCE((p_data ->> 'total_amount')::NUMERIC, 0),
         p_data ->> 'memo',
         p_dedupe_key,
         NOW())
    RETURNING id INTO v_new_id;

    RETURN json_build_object(
        'ok',           TRUE,
        'id',           v_new_id,
        'is_duplicate', FALSE
    );
END;
$$;


-- ─────────────────────────────────────────────
-- 부분 인덱스: dedupe_key UNIQUE (operator_id 스코프)
-- 013에서 client_id + dedupe_key로 만들었으나,
-- operator_id 테넌트 기준으로 더 정확한 인덱스 추가.
-- ─────────────────────────────────────────────
CREATE UNIQUE INDEX IF NOT EXISTS idx_billing_logs_operator_dedupe
    ON client_billing_logs (operator_id, dedupe_key)
    WHERE dedupe_key IS NOT NULL;
