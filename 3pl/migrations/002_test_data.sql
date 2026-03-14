-- ═══════════════════════════════════════════
-- PackFlow 3PL SaaS — Test Data
-- TEST_MODE 전용 — 상용 배포 시 실행 금지
-- ═══════════════════════════════════════════

-- ── 운영사 ──
INSERT INTO operators (id, name, business_no, ceo_name, phone, email, address, plan) VALUES
(1, '패킹플로우물류', '123-45-67890', '김대표', '02-1234-5678', 'admin@packflow.kr', '서울시 강남구 테헤란로 123', 'growth'),
(2, '스마트3PL', '234-56-78901', '이사장', '031-987-6543', 'info@smart3pl.kr', '경기도 용인시 처인구 물류단지 45', 'starter');

-- ── 사용자 (비밀번호: test1234) ──
INSERT INTO users (id, username, password_hash, name, role, operator_id, client_id, phone, email, is_approved) VALUES
-- 운영사1 사용자
(1, 'admin', 'test1234', '김관리', 'admin', 1, NULL, '010-1111-1111', 'admin@packflow.kr', TRUE),
(2, 'manager', 'test1234', '박매니저', 'manager', 1, NULL, '010-2222-2222', 'manager@packflow.kr', TRUE),
(3, 'warehouse1', 'test1234', '최창고', 'warehouse', 1, NULL, '010-3333-3333', 'wh@packflow.kr', TRUE),
-- 고객사 사용자
(4, 'client1', 'test1234', '정화주A', 'client_admin', 1, 1, '010-4444-4444', 'client1@example.com', TRUE),
(5, 'client2', 'test1234', '한화주B', 'client_admin', 1, 2, '010-5555-5555', 'client2@example.com', TRUE),
-- 패킹 사용자
(6, 'packer1', 'test1234', '강패커', 'packing_lead', 1, NULL, '010-6666-6666', 'packer1@packflow.kr', TRUE),
(7, 'packer2', 'test1234', '윤작업', 'packing_worker', 1, NULL, '010-7777-7777', 'packer2@packflow.kr', TRUE),
-- 운영사2 사용자
(8, 'admin2', 'test1234', '이관리', 'admin', 2, NULL, '010-8888-8888', 'admin@smart3pl.kr', TRUE);

-- ── 고객사 (화주) ──
INSERT INTO clients (id, operator_id, name, business_no, contact_name, contact_phone, contact_email, address, memo) VALUES
(1, 1, '(주)맛나식품', '345-67-89012', '김맛나', '010-1000-1001', 'food@matna.kr', '서울시 성동구 왕십리로 88', '냉장/냉동 혼합 보관'),
(2, 1, '비타민마트', '456-78-90123', '이비타', '010-1000-1002', 'vita@vitamart.kr', '경기도 성남시 분당구 판교역로 10', '상온 보관'),
(3, 1, '스마트가전', '567-89-01234', '박스마', '010-1000-1003', 'smart@sgadget.kr', '서울시 중구 을지로 200', '고가 제품 주의');

-- ── 창고 ──
INSERT INTO warehouses (id, operator_id, name, address, storage_type, memo) VALUES
(1, 1, '용인 제1센터', '경기도 용인시 처인구 백암면 물류로 100', 'ambient', '상온 메인 센터'),
(2, 1, '김포 냉장센터', '경기도 김포시 대곶면 율마로 55', 'cold', '냉장/냉동 전용'),
(3, 2, '인천 물류센터', '인천시 중구 신흥동 물류단지 12', 'ambient', '스마트3PL 메인');

-- ── 창고 구역 ──
INSERT INTO warehouse_zones (id, warehouse_id, name, storage_temp, memo) VALUES
(1, 1, 'A동 (일반)', 'ambient', '일반 상온 보관'),
(2, 1, 'B동 (대형)', 'ambient', '대형 화물'),
(3, 2, 'C동 (냉장)', 'cold', '0~5도'),
(4, 2, 'D동 (냉동)', 'frozen', '-18도 이하');

-- ── 로케이션 ──
INSERT INTO warehouse_locations (id, zone_id, code) VALUES
(1, 1, 'A-01-01'), (2, 1, 'A-01-02'), (3, 1, 'A-01-03'),
(4, 1, 'A-02-01'), (5, 1, 'A-02-02'),
(6, 2, 'B-01-01'), (7, 2, 'B-01-02'),
(8, 3, 'C-01-01'), (9, 3, 'C-01-02'),
(10, 4, 'D-01-01'), (11, 4, 'D-01-02');

-- ── SKU (상품) ──
INSERT INTO skus (id, operator_id, client_id, sku_code, barcode, name, category, unit, storage_temp, weight_g) VALUES
-- 맛나식품
(1, 1, 1, 'MN-001', '8801234567890', '맛나라면 5입', '식품', 'BOX', 'ambient', 600),
(2, 1, 1, 'MN-002', '8801234567891', '맛나김치 1kg', '식품', 'EA', 'cold', 1000),
(3, 1, 1, 'MN-003', '8801234567892', '맛나만두 500g', '식품', 'EA', 'frozen', 500),
-- 비타민마트
(4, 1, 2, 'VT-001', '8802345678901', '멀티비타민 60정', '건강식품', 'EA', 'ambient', 120),
(5, 1, 2, 'VT-002', '8802345678902', '오메가3 90정', '건강식품', 'EA', 'ambient', 150),
(6, 1, 2, 'VT-003', '8802345678903', '프로바이오틱스 30포', '건강식품', 'BOX', 'cold', 200),
-- 스마트가전
(7, 1, 3, 'SG-001', '8803456789012', '미니 블렌더', '가전', 'EA', 'ambient', 1500),
(8, 1, 3, 'SG-002', '8803456789013', '무선 이어폰', '가전', 'EA', 'ambient', 50),
(9, 1, 3, 'SG-003', '8803456789014', '보조배터리 10000mAh', '가전', 'EA', 'ambient', 200);

-- ── 재고 ──
INSERT INTO inventory_stock (operator_id, sku_id, location_id, quantity, lot_number, expiry_date) VALUES
(1, 1, 1, 250, 'LOT-2026-01', '2027-01-15'),
(1, 1, 2, 100, 'LOT-2026-02', '2027-03-20'),
(1, 2, 8, 80, 'LOT-2026-01', '2026-06-30'),
(1, 3, 10, 150, 'LOT-2026-01', '2026-12-31'),
(1, 4, 3, 500, 'LOT-2026-01', '2027-06-15'),
(1, 5, 4, 300, 'LOT-2026-01', '2027-08-20'),
(1, 6, 9, 200, 'LOT-2026-01', '2026-09-10'),
(1, 7, 6, 40, NULL, NULL),
(1, 8, 5, 120, NULL, NULL),
(1, 9, 5, 80, NULL, NULL);

-- ── 주문 ──
INSERT INTO orders (id, operator_id, client_id, channel, order_no, status, recipient_name, recipient_phone, recipient_address, memo, order_date) VALUES
(1, 1, 1, 'coupang', 'CP-2026031401', 'pending', '홍길동', '010-9999-0001', '서울시 강남구 역삼동 123-45', '빠른배송', '2026-03-14 09:00:00+09'),
(2, 1, 1, 'naver', 'NV-2026031402', 'confirmed', '김철수', '010-9999-0002', '경기도 수원시 팔달구 인계동 67', '', '2026-03-14 09:30:00+09'),
(3, 1, 2, 'direct', 'DR-2026031403', 'packing', '이영희', '010-9999-0003', '서울시 송파구 잠실동 200', '포장 주의', '2026-03-14 10:00:00+09'),
(4, 1, 2, 'cafe24', 'C4-2026031404', 'shipped', '박지민', '010-9999-0004', '부산시 해운대구 좌동 55', '', '2026-03-13 14:00:00+09'),
(5, 1, 3, 'coupang', 'CP-2026031405', 'delivered', '최수진', '010-9999-0005', '대전시 서구 둔산동 88', '', '2026-03-12 11:00:00+09'),
(6, 1, 3, 'naver', 'NV-2026031406', 'pending', '정민수', '010-9999-0006', '인천시 남동구 구월동 33', '부재시 경비실', '2026-03-14 11:30:00+09'),
(7, 1, 1, 'coupang', 'CP-2026031407', 'cancelled', '강예린', '010-9999-0007', '서울시 마포구 합정동 12', '취소 요청', '2026-03-14 08:00:00+09');

-- ── 주문 상세 ──
INSERT INTO order_items (order_id, sku_id, quantity, unit_price) VALUES
(1, 1, 3, 4500),   -- 맛나라면 3박스
(1, 2, 1, 8900),   -- 맛나김치 1개
(2, 3, 5, 5500),   -- 맛나만두 5개
(3, 4, 2, 15000),  -- 멀티비타민 2개
(3, 5, 1, 22000),  -- 오메가3 1개
(4, 6, 3, 18000),  -- 프로바이오틱스 3박스
(5, 7, 1, 45000),  -- 미니블렌더 1개
(5, 8, 2, 35000),  -- 무선이어폰 2개
(6, 9, 1, 19000),  -- 보조배터리 1개
(7, 1, 10, 4500);  -- 취소 주문

-- ── 배송 ──
INSERT INTO shipments (operator_id, order_id, courier, invoice_no, status, shipped_at, delivered_at) VALUES
(1, 4, 'cj', '1234567890123', 'in_transit', '2026-03-13 16:00:00+09', NULL),
(1, 5, 'hanjin', '9876543210987', 'delivered', '2026-03-12 15:00:00+09', '2026-03-13 10:30:00+09');

-- ── 패킹 작업 ──
INSERT INTO packing_jobs (operator_id, user_id, order_id, scanned_barcode, scanned_items, status, started_at, completed_at) VALUES
(1, 6, 3, '8802345678901', '[{"barcode":"8802345678901","name":"멀티비타민 60정","qty":2},{"barcode":"8802345678902","name":"오메가3 90정","qty":1}]', 'recording', '2026-03-14 10:30:00+09', NULL),
(1, 7, 4, '8802345678903', '[{"barcode":"8802345678903","name":"프로바이오틱스 30포","qty":3}]', 'completed', '2026-03-13 15:00:00+09', '2026-03-13 15:25:00+09'),
(1, 6, 5, '8803456789012', '[{"barcode":"8803456789012","name":"미니 블렌더","qty":1},{"barcode":"8803456789013","name":"무선 이어폰","qty":2}]', 'completed', '2026-03-12 14:00:00+09', '2026-03-12 14:35:00+09');

-- ── 재고 이동 이력 ──
INSERT INTO inventory_movements (operator_id, sku_id, location_id, movement_type, quantity, order_id, lot_number, memo, user_id) VALUES
(1, 1, 1, 'inbound', 300, NULL, 'LOT-2026-01', '입고 — 맛나식품 정기 입고', 1),
(1, 1, 2, 'inbound', 100, NULL, 'LOT-2026-02', '입고 — 추가 입고', 1),
(1, 1, 1, 'outbound', -3, 1, 'LOT-2026-01', '출고 — 주문#1', 3),
(1, 3, 10, 'inbound', 200, NULL, 'LOT-2026-01', '입고 — 맛나만두', 1),
(1, 3, 10, 'outbound', -5, 2, 'LOT-2026-01', '출고 — 주문#2', 3),
(1, 7, 6, 'inbound', 50, NULL, NULL, '입고 — 미니블렌더', 1),
(1, 7, 6, 'outbound', -1, 5, NULL, '출고 — 주문#5', 6),
(1, 8, 5, 'inbound', 130, NULL, NULL, '입고 — 무선이어폰', 1),
(1, 8, 5, 'outbound', -2, 5, NULL, '출고 — 주문#5', 6),
(1, 4, 3, 'adjust', -10, NULL, 'LOT-2026-01', '재고조정 — 파손', 2);

-- ── 과금 사용량 ──
INSERT INTO billing_usage (operator_id, year_month, metric, count, unit_price) VALUES
(1, '2026-03', 'orders', 7, 100),
(1, '2026-03', 'shipments', 2, 200),
(1, '2026-03', 'storage_days', 9, 50),
(1, '2026-02', 'orders', 45, 100),
(1, '2026-02', 'shipments', 38, 200),
(1, '2026-02', 'storage_days', 9, 50);

-- ── 청구서 ──
INSERT INTO billing_invoices (operator_id, year_month, total_amount, status, paid_at) VALUES
(1, '2026-02', 162050, 'paid', '2026-03-05 10:00:00+09'),
(1, '2026-03', 0, 'pending', NULL);
