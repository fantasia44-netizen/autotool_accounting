# PackFlow 3PL SaaS — 2026-03-15 구조 설계 상세 요약서

> **목적**: 오늘 구현한 7개 Task(A~G)의 전체 아키텍처를 외부 AI에 검토 요청하기 위한 상세 문서
> **검토 요청 사항**: 설계 일관성, 확장성, 보안, 잠재적 버그, 개선점

---

## 1. 시스템 개요

### 1.1 기술 스택
- **Backend**: Flask (Python 3.14) + Supabase (PostgreSQL)
- **Frontend**: Jinja2 + Bootstrap 5 (SSR, SPA 아님)
- **ORM 없음**: Supabase REST API 직접 호출 (Repository 패턴)
- **Multi-tenant**: operator_id 기반 데이터 격리
- **인증**: Flask-Login + Role-based (@role_required)

### 1.2 디렉토리 구조
```
3pl/
├── app.py                          # Flask 앱 팩토리, repo 등록
├── db_utils.py                     # get_repo(), DemoProxy (Supabase 미연결 시 목업)
├── blueprints/operator/views.py    # 운영자 포탈 모든 라우트 (단일 파일, ~1100줄)
├── repositories/
│   ├── base.py                     # BaseRepository (_query, _insert, _update, _delete)
│   ├── inventory_repo.py           # SKU, 재고, 입출고 이력
│   ├── order_repo.py               # 주문, 출고(shipments), 상태로그
│   ├── client_repo.py              # 고객사 CRUD, 요금표(client_rates)
│   ├── client_marketplace_repo.py  # 마켓플레이스 API 인증정보
│   ├── client_billing_repo.py      # [신규] 과금 로그, 정산서
│   └── warehouse_repo.py           # 창고, 존, 로케이션
├── services/
│   └── client_billing_service.py   # [신규] 자동 과금 계산 엔진
├── migrations/
│   ├── 006_outbound_enhanced.sql   # [신규] shipments 테이블 확장
│   └── 007_billing_enhanced.sql    # [신규] 과금/정산 테이블
└── templates/operator/
    ├── client_detail.html          # 고객사 상세 (요금표+SKU+마켓플레이스)
    ├── client_billing.html         # [신규] 월별 정산서
    ├── orders.html                 # 주문관리 (고객사 필터 추가)
    ├── inbound.html                # 입고관리 (고객사→동적 SKU)
    ├── shipments.html              # 출고관리 (반품/이동 탭 추가)
    └── skus.html                   # 상품마스터 (엑셀 업로드 추가)
```

---

## 2. 데이터 모델 (DB 스키마 변경)

### 2.1 Migration 006 — 출고관리 확장
```sql
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS shipment_type TEXT DEFAULT 'normal';
-- 값: 'normal'(일반출고), 'return'(반품출고), 'transfer'(창고이동)

ALTER TABLE shipments ADD COLUMN IF NOT EXISTS client_id BIGINT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS from_warehouse_id BIGINT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS to_warehouse_id BIGINT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS reason TEXT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS sku_id BIGINT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS quantity INT;

CREATE INDEX idx_shipments_type ON shipments(shipment_type);
CREATE INDEX idx_shipments_client ON shipments(client_id);
```

**설계 의도**:
- 기존 `shipments` 테이블이 일반 출고(송장추적)만 담당 → `shipment_type`으로 3가지 출고 유형 통합
- `from/to_warehouse_id`는 창고이동 전용, 일반/반품출고에서는 NULL
- `sku_id`, `quantity`는 반품/이동에서 단품 단위 처리용

### 2.2 Migration 007 — 과금/정산 체계
```sql
-- 1) 기존 client_rates에 카테고리 추가
ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'custom';

-- 2) 과금 로그 (이벤트 발생 시마다 1행씩 적재)
CREATE TABLE client_billing_logs (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL,
    client_id BIGINT NOT NULL,
    rate_id BIGINT,              -- client_rates FK (nullable, 수동 등록 시 NULL)
    order_id BIGINT,             -- 연관 주문 (nullable)
    year_month TEXT NOT NULL,    -- '2026-03' 형식 (파티션 키)
    fee_name TEXT NOT NULL,
    category TEXT DEFAULT 'custom',
    quantity NUMERIC(12,2) DEFAULT 1,
    unit_price NUMERIC(12,2) DEFAULT 0,
    total_amount NUMERIC(12,2) DEFAULT 0,
    memo TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3) 정산서 (고객사×월 단위, UNIQUE 제약)
CREATE TABLE client_invoices (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL,
    client_id BIGINT NOT NULL,
    year_month TEXT NOT NULL,
    total_amount NUMERIC(12,2) DEFAULT 0,
    status TEXT DEFAULT 'draft', -- draft → confirmed → sent → paid
    confirmed_at TIMESTAMPTZ,
    memo TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(operator_id, client_id, year_month)
);
```

**카테고리 체계**:
| 카테고리 | DB값 | 한글명 | 예시 항목 |
|----------|------|--------|-----------|
| 입고비 | inbound | 입고비 | 입고검수비, 상차비, 하차비 |
| 출고비 | outbound | 출고비 | 출고작업비, 합포장추가비 |
| 보관비 | storage | 보관비 | 일반보관, 냉장보관, 냉동보관 |
| 택배비 | courier | 택배비 | 기본택배비, 사이즈추가비, 중량추가비 |
| 부자재 | material | 부자재비 | 박스, 아이스팩, 드라이아이스, 완충재, 테이프 |
| 반품 | return | 반품비 | 반품수수료, 반품검수비 |
| 부가서비스 | vas | 부가서비스 | 라벨부착, 키팅, 사진촬영 |
| 기타 | custom | 기타 | 사용자 자유 입력 |

---

## 3. 레이어 아키텍처

### 3.1 Repository Layer

#### BaseRepository (base.py)
```python
class BaseRepository:
    def __init__(self, supabase_client, operator_id):
        self.sb = supabase_client
        self.operator_id = operator_id

    def _query(table, filters, columns, order_by, order_desc, limit)
    def _insert(table, data)  # operator_id 자동 주입
    def _update(table, id, data)
    def _delete(table, id)
```
- 모든 쿼리에 `operator_id` 필터 자동 적용 (멀티테넌트)
- Supabase REST API 직접 호출 (ORM 없음)

#### ClientBillingRepository (신규)
```python
class ClientBillingRepository(BaseRepository):
    LOG_TABLE = 'client_billing_logs'
    INVOICE_TABLE = 'client_invoices'

    def log_fee(data)                                    # 과금 1건 기록
    def list_fees(client_id, year_month, category)       # 조회
    def get_monthly_summary(client_id, year_month)       # 카테고리별 집계
    # → returns {'by_category': {cat: amount}, 'total': N, 'items': [rows]}
    def get_invoice(client_id, year_month)               # 정산서 조회
    def create_invoice(data) / update_invoice(id, data)  # 정산서 CRUD
```

#### OrderRepository (수정)
```python
# list_shipments() 필터 추가
def list_shipments(order_id, status, shipment_type, client_id, limit=200)
# shipment_type: 'normal' | 'return' | 'transfer'
```

### 3.2 Service Layer

#### client_billing_service.py (신규)
**순수 함수 설계** — 클래스 없이 함수만으로 구성, repo를 인자로 받음.

```python
# 자동 과금 기록 함수들
record_inbound_fee(billing_repo, rate_repo, client_id, quantity, memo)
record_outbound_fee(billing_repo, rate_repo, client_id, order_id, memo)
record_packing_fee(billing_repo, rate_repo, client_id, order_id, materials)
record_return_fee(billing_repo, rate_repo, client_id, memo)
calculate_storage_fee(billing_repo, rate_repo, inv_repo, client_id, year_month)
```

**동작 방식**:
1. `rate_repo.list_rates(client_id)` → 해당 고객사 요금표 전체 조회
2. `category` 필터링 → 해당 카테고리 요금만 추출
3. 각 요금 항목마다 `billing_repo.log_fee()` → `client_billing_logs` 적재
4. 금액 = `unit_price × quantity`

**프리셋 데이터** (21개 항목):
```python
RATE_PRESETS = [
    {'category': 'inbound', 'fee_name': '입고검수비', 'unit_label': '건', 'amount': 0},
    {'category': 'inbound', 'fee_name': '상차비', 'unit_label': '팔레트', 'amount': 0},
    {'category': 'inbound', 'fee_name': '하차비', 'unit_label': '팔레트', 'amount': 0},
    {'category': 'outbound', 'fee_name': '출고작업비', 'unit_label': '건', 'amount': 0},
    {'category': 'outbound', 'fee_name': '합포장추가비', 'unit_label': '건', 'amount': 0},
    {'category': 'storage', 'fee_name': '일반보관비', 'unit_label': '일', 'amount': 0},
    {'category': 'storage', 'fee_name': '냉장보관비', 'unit_label': '일', 'amount': 0},
    {'category': 'storage', 'fee_name': '냉동보관비', 'unit_label': '일', 'amount': 0},
    {'category': 'courier', 'fee_name': '기본택배비', 'unit_label': '건', 'amount': 0},
    {'category': 'courier', 'fee_name': '사이즈추가비', 'unit_label': '건', 'amount': 0},
    {'category': 'courier', 'fee_name': '중량추가비', 'unit_label': 'kg', 'amount': 0},
    {'category': 'material', 'fee_name': '박스', 'unit_label': '개', 'amount': 0},
    {'category': 'material', 'fee_name': '아이스팩', 'unit_label': '개', 'amount': 0},
    {'category': 'material', 'fee_name': '드라이아이스', 'unit_label': '개', 'amount': 0},
    {'category': 'material', 'fee_name': '완충재', 'unit_label': '개', 'amount': 0},
    {'category': 'material', 'fee_name': '테이프', 'unit_label': '개', 'amount': 0},
    {'category': 'return', 'fee_name': '반품수수료', 'unit_label': '건', 'amount': 0},
    {'category': 'return', 'fee_name': '반품검수비', 'unit_label': '건', 'amount': 0},
    {'category': 'vas', 'fee_name': '라벨부착', 'unit_label': '건', 'amount': 0},
    {'category': 'vas', 'fee_name': '키팅', 'unit_label': '건', 'amount': 0},
    {'category': 'vas', 'fee_name': '사진촬영', 'unit_label': 'SKU', 'amount': 0},
]
```

### 3.3 View Layer (blueprints/operator/views.py)

**단일 파일 약 1,100줄** — 운영자 포탈의 모든 라우트 포함.

#### 신규 라우트 (9개)
| 라우트 | 메서드 | 경로 | 기능 |
|--------|--------|------|------|
| `client_sku_create` | POST | `/clients/<id>/skus` | 고객사 상세에서 SKU 추가 |
| `client_sku_update` | POST | `/clients/<id>/skus/<id>/update` | 고객사 SKU 수정 |
| `sku_sample_excel` | GET | `/skus/sample-excel` | 엑셀 샘플 다운로드 |
| `sku_bulk_upload` | POST | `/skus/bulk-upload` | 엑셀 일괄 업로드 |
| `api_skus_by_client` | GET | `/api/skus-by-client?client_id=N` | JSON API (동적 SKU) |
| `shipment_return_create` | POST | `/shipments/return` | 반품출고 생성 |
| `shipment_transfer_create` | POST | `/shipments/transfer` | 창고이동 생성 |
| `client_rate_preset` | POST | `/clients/<id>/rates/preset` | 요금 프리셋 일괄 추가 |
| `client_billing` | GET | `/clients/<id>/billing` | 월별 정산서 조회 |
| `client_billing_confirm` | POST | `/clients/<id>/billing/confirm` | 정산서 확정 |

#### 수정된 라우트 (5개)
| 라우트 | 변경 내용 |
|--------|-----------|
| `orders()` | client_id 필터 추가, clients 목록 + client_map 전달 |
| `inbound()` | clients 목록 전달, POST 성공 시 `record_inbound_fee()` 훅 |
| `shipments()` | shipment_type/client_id 필터, clients/warehouses/skus 전달 |
| `client_detail()` | client_skus 전달 |
| `order_status_update()` | status='shipped' 시 `record_outbound_fee()` 훅 |
| `client_rate_create()` | category 필드 추가, 한도 20→50 |

#### 과금 훅 연결 (4곳)
```
1. inbound() POST 성공 → record_inbound_fee()
2. order_status_update() shipped → record_outbound_fee()
3. shipment_return_create() 성공 → record_return_fee()
4. (패킹 기능은 미구현 — record_packing_fee() 준비만 됨)
```

모든 훅은 `try/except`로 감싸져 있어 과금 오류가 핵심 업무를 차단하지 않음:
```python
try:
    record_inbound_fee(billing_repo, rate_repo, client_id, ...)
except Exception:
    pass  # 과금 실패해도 입고는 정상 처리
```

---

## 4. Task별 구현 상세

### Task A+F: 고객사 상세 — 상품관리 + 바코드 필수

**UI 변경** (`client_detail.html`):
- 요금표 섹션: "프리셋 추가" 버튼 (카테고리 체크박스 → 일괄 생성)
- 요금 추가 폼: category 드롭다운 추가, 단위 확장 (건/SKU/일/kg/박스/팔레트/개/CBM)
- 상품(SKU) 섹션: 샘플 다운로드, 엑셀 업로드, 단건 추가 폼, 목록 테이블
- 바코드 필수 검증: `sku_create()`, `client_sku_create()`에서 서버사이드 체크

**단위 옵션 통일**: EA(개), BOX(박스), PALLET(팔레트), PACK(팩), SET(세트)

### Task E: 엑셀 일괄 업로드

**샘플 다운로드** (`sku_sample_excel`):
- openpyxl로 .xlsx 생성
- 헤더: sku_code(필수), barcode(필수), name(필수), category, unit, storage_temp, weight_g, memo
- 2행에 예시 데이터 포함

**업로드 처리** (`sku_bulk_upload`):
- openpyxl로 파싱
- barcode 필수 검증, 빈 값 → 해당 행 스킵
- 성공/실패 카운트 flash 메시지
- client_id 옵션 (폼에서 선택 가능)

### Task B: 입고관리 고객사 연동

**동적 SKU 드롭다운**:
```
1. 고객사 select 변경 → JS loadClientSkus(clientId)
2. fetch('/operator/api/skus-by-client?client_id=N')
3. SKU select 옵션 동적 교체 (data-barcode, data-name 속성)
4. SKU 선택 시 바코드/상품명 자동 표시
```

### Task C: 주문관리 고객사 단위

- 필터바에 고객사 드롭다운 추가
- 테이블에 "고객사" 컬럼 추가 (`client_map.get(o.client_id, '-')`)
- 상태 탭 전환 시 client_id 파라미터 유지

### Task D: 출고관리 강화

**3탭 구조**:
- **일반출고**: 기존 송장 기반 출고 (주문ID, 택배사, 송장번호)
- **반품출고**: 고객사 선택 → SKU → 수량 → 반품사유 → 생성 시 `shipment_type='return'`
- **창고이동**: 출발창고 → 도착창고 → SKU → 수량 → 생성 시 `transfer_out` + `transfer_in` 재고이동 기록

**반품출고 처리 흐름**:
```
POST /shipments/return
→ create_shipment(shipment_type='return', client_id, sku_id, quantity, reason)
→ record_return_fee() [과금 훅]
→ redirect /shipments?type=return
```

**창고이동 처리 흐름**:
```
POST /shipments/transfer
→ create_shipment(shipment_type='transfer', from_warehouse_id, to_warehouse_id, sku_id, quantity)
→ record_movement(type='transfer_out', warehouse_id=from)
→ record_movement(type='transfer_in', warehouse_id=to)
→ redirect /shipments?type=transfer
```

### Task G: 3PL 과금 체계 + 자동 정산

**과금 흐름 전체 다이어그램**:
```
[이벤트 발생]
    ↓
[views.py 훅] → client_billing_service.record_xxx_fee()
    ↓
[rate_repo.list_rates(client_id)] → 해당 카테고리 요금표 조회
    ↓
[billing_repo.log_fee()] → client_billing_logs 적재
    ↓
[client_billing 페이지] → get_monthly_summary() → 카테고리별 집계 + 상세 내역
    ↓
[정산서 확정] → client_invoices 생성/업데이트 (status: draft→confirmed)
```

**요금 프리셋 시스템**:
- 고객사 상세 → "프리셋 추가" → 카테고리 체크박스 선택 → POST
- 선택한 카테고리의 프리셋 항목을 `client_rates`에 일괄 INSERT
- 금액은 0원으로 생성 → 운영자가 개별 수정

**월별 정산서 페이지** (`/clients/<id>/billing`):
- 월 선택 (input type=month)
- 요약 카드: 합계 + 카테고리별 소계
- 정산서 상태 뱃지: 초안/확정/발송/입금완료
- "정산서 확정" 버튼 → invoice 생성 + status='confirmed'
- 상세 테이블: 카테고리, 항목명, 수량, 단가, 금액, 메모, 일시

---

## 5. DemoProxy 호환성

Supabase 미연결 시 `DemoProxy`가 모든 repo 메서드를 가로채 빈 데이터 반환.

**추가된 DemoProxy 핸들러**:
```python
if name == 'get_monthly_summary':
    return {'by_category': {}, 'total': 0, 'items': []}
```

---

## 6. 수정 파일 전체 목록

| 파일 | 작업 | 변경 규모 |
|------|------|-----------|
| `blueprints/operator/views.py` | 라우트 9개 추가 + 5개 수정 + 과금 훅 4곳 | 대규모 (~300줄 추가) |
| `templates/operator/client_detail.html` | SKU 섹션 + 요금 프리셋 + 정산 버튼 | 대규모 |
| `templates/operator/client_billing.html` | **신규** — 월별 정산서 페이지 | 신규 (~98줄) |
| `templates/operator/orders.html` | 고객사 필터 + 컬럼 추가 | 중규모 |
| `templates/operator/inbound.html` | 고객사 선택 + 동적 SKU JS | 중규모 |
| `templates/operator/shipments.html` | 3탭 구조로 전면 리뉴얼 | 대규모 |
| `templates/operator/skus.html` | 엑셀 업로드/샘플 + 바코드 필수 + 단위 확장 | 중규모 |
| `migrations/006_outbound_enhanced.sql` | **신규** — shipments 확장 | 신규 |
| `migrations/007_billing_enhanced.sql` | **신규** — 과금/정산 테이블 | 신규 |
| `repositories/client_billing_repo.py` | **신규** — 과금 로그/정산서 CRUD | 신규 (~60줄) |
| `repositories/order_repo.py` | shipment 쿼리 필터 추가 | 소규모 |
| `services/client_billing_service.py` | **신규** — 자동 과금 엔진 + 프리셋 | 신규 (~160줄) |
| `app.py` | client_billing repo 등록 | 소규모 (2줄) |
| `db_utils.py` | DemoProxy 핸들러 추가 | 소규모 (2줄) |

---

## 7. 검토 요청 포인트

### 7.1 아키텍처 관련
1. **views.py 단일 파일 비대화** (~1,100줄) — 분리 필요한가? Blueprint 내 모듈 분리 방안은?
2. **Service Layer의 순수 함수 설계** — 클래스 vs 함수, DI 패턴 적절성
3. **과금 훅의 try/except pass** — 사일런트 실패가 괜찮은가? 로깅은?
4. **year_month TEXT 필드** — DATE 타입 vs TEXT 트레이드오프
5. **client_billing_logs에 operator_id 중복** — client_id로 역추적 가능한데 필요한가?

### 7.2 데이터 모델 관련
1. **shipments 테이블 확장** vs 별도 `return_shipments`, `transfers` 테이블 — 정규화 관점
2. **client_rates.category + amount** — 단일 amount로 정률/정액 구분이 가능한가?
3. **client_invoices UNIQUE(operator_id, client_id, year_month)** — 수정분 처리 방법
4. **FK 제약 없음** (rate_id, order_id 등) — Supabase REST API 한계인가, 의도인가?

### 7.3 보안/안정성 관련
1. **엑셀 업로드** — 파일 크기 제한, 악성 파일 검증 부재
2. **api_skus_by_client** — 인증 체크는 되어 있는가? (다른 operator의 client 접근 가능성)
3. **과금 금액 조작** — client-side에서 amount 변경 가능한가?

### 7.4 기능 완성도 관련
1. **보관비 자동 계산** (`calculate_storage_fee`) — 호출 트리거 없음 (수동 or 스케줄러?)
2. **패킹 과금** (`record_packing_fee`) — 패킹 화면에서 부자재 입력 UI 없음
3. **정산서 발송** — 'sent' 상태 전환 기능 미구현 (이메일/PDF 연동 필요?)
4. **반품출고** — 재고 재입고 처리 없음 (inventory_movement 기록만 하고 stock 미반영?)
5. **창고이동** — stock 차감/증가 처리 여부 확인 필요

### 7.5 UX 관련
1. **Jinja2 dict.items 트랩** — `summary.items` → `summary['items']` (이미 수정 완료)
2. **프리셋 중복 추가** — 같은 카테고리 프리셋 두 번 추가 시 중복 체크 없음
3. **정산서 확정 후 추가 과금** — 확정 후에도 billing_logs에 기록이 추가될 수 있음

---

## 8. 향후 로드맵 (미구현)

- [ ] 보관비 월말 일괄 계산 스케줄러 (calculate_storage_fee 트리거)
- [ ] 패킹 화면 부자재 입력 → record_packing_fee 연결
- [ ] 정산서 PDF 다운로드 / 이메일 발송
- [ ] 과금 수동 등록/수정 UI
- [ ] 과금 로그 삭제/취소 기능
- [ ] 반품출고 재고 재입고 자동 처리
- [ ] 클라이언트(고객사) 포탈에서 정산서 조회
