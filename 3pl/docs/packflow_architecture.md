# PackFlow — 시스템 아키텍처 및 구조 설계서

**작성일**: 2026-03-18
**버전**: 2.1 (현장모드 포함)
**시스템**: 3PL SaaS 물류 관리 플랫폼

---

## 1. 시스템 개요

PackFlow는 3PL(Third-Party Logistics) 사업자를 위한 SaaS 형태의 물류 관리 플랫폼이다.
Flask + Supabase(PostgREST) 기반으로 구축되며, 멀티테넌트 구조로 운영사별 데이터를 격리한다.

### 1.1 핵심 기능 영역
- **주문관리**: 마켓플레이스 연동, 주문 수집/상태관리
- **재고관리**: SKU/로케이션 기반 재고, 2-Phase Commit, FIFO
- **입출고**: 입고/출고/반품/창고이동 프로세스
- **피킹**: 주문별/상품별/로케이션별 피킹리스트 자동생성
- **패킹/검수**: 영상촬영 + 바코드 검수로 오배송 방지
- **현장모드**: 모바일 바코드 스캔 기반 입고/이동/실사/상차
- **과금/정산**: 건별 과금, 월별 청구서, P&L 분석
- **감사로그**: 전체 CUD 자동 기록, 복원 기능

---

## 2. 기술 스택

| 구분 | 기술 |
|------|------|
| **Backend** | Python 3.11 + Flask 3.x |
| **Database** | Supabase (PostgreSQL 15 + PostgREST) |
| **ORM/Query** | Supabase Python Client (PostgREST API) |
| **인증** | Flask-Login + 세션 기반 |
| **CSRF** | Flask-WTF CSRFProtect |
| **Frontend** | Jinja2 + Bootstrap 5 + Bootstrap Icons |
| **파일저장** | Supabase Storage (packing-videos 버킷) |
| **시간대** | KST (Asia/Seoul) 통일 — tz_utils.py |
| **배포** | Python 직접 실행 (run.py) |

---

## 3. 디렉토리 구조

```
3pl/
├── app.py                    # Flask Application Factory
├── config.py                 # 환경 설정 (dev/prod)
├── run.py                    # 실행 엔트리포인트
├── db_utils.py               # Repository 팩토리 (get_repo)
├── models.py                 # User, ROLES, PAGE_REGISTRY, MENU_GROUPS
├── auth.py                   # 로그인/회원가입 Blueprint
│
├── repositories/             # 데이터 접근 계층 (Repository Pattern)
│   ├── base.py               # BaseRepository (CRUD + 감사로그 + 소프트삭제)
│   ├── inventory_repo.py     # SKU, 재고, 예약, 수불부
│   ├── warehouse_repo.py     # 창고, 구역, 로케이션
│   ├── order_repo.py         # 주문, 주문아이템, 출고, 상태로그
│   ├── picking_repo.py       # 피킹리스트, 피킹항목
│   ├── packing_repo.py       # 패킹작업, 영상관리
│   ├── client_repo.py        # 고객사 CRUD
│   ├── client_rate_repo.py   # 고객사별 과금 단가
│   ├── client_billing_repo.py # 과금 로그 (건별)
│   ├── billing_repo.py       # 청구서 (월별)
│   ├── client_marketplace_repo.py # 마켓플레이스 연동 설정
│   ├── user_repo.py          # 사용자 CRUD
│   ├── audit_repo.py         # 감사 로그 조회/복원
│   └── finance_repo.py       # P&L, 비용 관리
│
├── services/                 # 비즈니스 로직 계층
│   ├── warehouse_service.py  # 입고/출고 처리 (재고+이력)
│   ├── inventory_service.py  # 2-Phase Commit (예약→확정→해제)
│   ├── picking_service.py    # 피킹리스트 자동생성 (FIFO)
│   ├── client_billing_service.py # 건별 과금 기록
│   ├── shipment_guard.py     # 출고 차단 검증
│   ├── scan_validator.py     # 바코드 스캔 검증 (오출고 방지)
│   ├── tz_utils.py           # KST 타임존 유틸리티
│   └── finance_service.py    # P&L 계산, 비용 분류
│
├── blueprints/               # Flask 블루프린트 (포털별)
│   ├── operator/             # 운영자 포털
│   │   ├── __init__.py       # operator_bp 정의, _require_operator
│   │   ├── inventory_views.py # 재고현황, 입고, 조정, 수불부, SKU
│   │   ├── order_views.py    # 주문, 피킹, 출고, 반품, 이동, 패킹
│   │   ├── admin_views.py    # 감사로그, 경영분석(P&L)
│   │   └── (client_views, warehouse_views 등)
│   ├── client/               # 고객사 포털
│   │   └── views.py          # 재고조회, 주문현황, 영상확인, 과금내역
│   ├── packing/              # 패킹센터 포털 + 현장모드
│   │   └── views.py          # 대시보드, 피킹, 촬영, 현장스캔 전체
│   └── api/                  # REST API (외부 연동)
│       └── views.py          # 토큰 인증 기반 API
│
├── templates/                # Jinja2 템플릿
│   ├── base.html             # 공통 레이아웃 (사이드바, 탑바)
│   ├── operator/             # 운영자 템플릿 (20+)
│   ├── client/               # 고객사 템플릿
│   ├── packing/              # 패킹 + 현장모드 템플릿
│   │   ├── dashboard.html
│   │   ├── picking.html      # 피킹 스캔 (모바일 최적화)
│   │   ├── recording.html    # 촬영+검수 (카메라+바코드+영상)
│   │   ├── scan.html         # 단순 바코드 조회
│   │   ├── queue.html, stats.html
│   │   ├── field_dashboard.html   # 현장모드 홈
│   │   ├── field_inbound.html     # 입고 스캔
│   │   ├── field_transfer.html    # 창고이동 스캔
│   │   ├── field_stockcheck.html  # 재고실사
│   │   └── field_shipping.html    # 출고상차 스캔
│   └── landing/              # 랜딩 페이지
│
├── static/                   # 정적 파일
│   ├── css/app.css           # 디자인 시스템
│   └── js/                   # (현재 인라인 JS 위주)
│
├── migrations/               # DB 마이그레이션 SQL
│   ├── 001_initial.sql ~ 015_shipments_extend.sql
│
└── docs/                     # 문서
    └── packflow_architecture.md  # (이 문서)
```

---

## 4. 데이터베이스 설계 (Supabase PostgreSQL)

### 4.1 테넌트 격리
모든 주요 테이블에 `operator_id` 컬럼이 있으며, BaseRepository에서 자동으로 필터링한다.
```
operator_id BIGINT NOT NULL  -- 운영사 ID (멀티테넌트 키)
```

### 4.2 핵심 테이블 ERD

```
┌──────────────────────────────────────────────────────────┐
│                    operators (운영사)                       │
│  id BIGSERIAL, name, business_no, plan_type, created_at    │
└──────────┬───────────────────────────────────────────────┘
           │ 1:N
┌──────────▼───────────────────────────────────────────────┐
│                     users (사용자)                          │
│  id, operator_id, username, password_hash, name,           │
│  role, client_id, is_approved, created_at                  │
│  ROLES: super_admin|owner|admin|manager|warehouse|cs|      │
│         viewer|client_admin|client_staff|client_viewer|     │
│         packing_lead|packing_worker                        │
└──────────────────────────────────────────────────────────┘
```

### 4.3 재고/창고 테이블

```
warehouses               warehouse_zones           warehouse_locations
┌──────────────┐        ┌──────────────────┐      ┌──────────────────┐
│ id           │ 1:N    │ id               │ 1:N  │ id               │
│ operator_id  ├───────►│ warehouse_id     ├─────►│ zone_id          │
│ name         │        │ name             │      │ code (A-01-01)   │
│ address      │        │ storage_temp     │      │ is_active        │
│ is_active    │        │   (ambient/cold/ │      │ storage_temp     │
└──────────────┘        │    frozen)       │      └──────────────────┘
                        └──────────────────┘

skus (상품마스터)                 inventory_stock (재고)
┌─────────────────────┐         ┌─────────────────────────┐
│ id                  │   1:N   │ id                      │
│ operator_id         ├────────►│ operator_id             │
│ client_id           │         │ sku_id                  │
│ sku_code            │         │ location_id             │
│ barcode             │         │ lot_number              │
│ name                │         │ quantity                │
│ category            │         │ reserved_qty            │
│ unit (EA/BOX/...)   │         │ expiry_date             │
│ storage_temp        │         │ updated_at              │
│ weight_g            │         │ UNIQUE(sku_id,          │
│ min_stock_qty       │         │   location_id,          │
│ memo                │         │   lot_number)           │
└─────────────────────┘         └─────────────────────────┘

inventory_movements (수불부)         inventory_reservations (2-Phase)
┌───────────────────────┐           ┌────────────────────────┐
│ id                    │           │ id                     │
│ operator_id           │           │ operator_id            │
│ sku_id                │           │ order_id               │
│ location_id           │           │ sku_id                 │
│ movement_type:        │           │ location_id            │
│   inbound|outbound|   │           │ lot_number             │
│   adjust|transfer_in| │           │ reserved_qty           │
│   transfer_out|       │           │ status:                │
│   return_in           │           │   reserved|committed|  │
│ quantity (+/-)        │           │   released             │
│ order_id              │           │ created_at             │
│ lot_number            │           │ committed_at           │
│ memo                  │           └────────────────────────┘
│ user_id               │
│ created_at            │
└───────────────────────┘
```

### 4.4 주문/출고 테이블

```
orders (주문)                        order_items (주문품목)
┌───────────────────────┐           ┌──────────────────┐
│ id                    │   1:N     │ order_id         │
│ operator_id           ├──────────►│ sku_id           │
│ client_id             │           │ quantity         │
│ order_no              │           │ qty              │
│ channel               │           │ weight_g         │
│ status:               │           └──────────────────┘
│   pending|confirmed|  │
│   picking_ready|      │           order_status_logs
│   picked|packed|      │           ┌──────────────────┐
│   shipped|cancelled|  │    1:N    │ order_id         │
│   hold                ├──────────►│ old_status       │
│ hold_flag             │           │ new_status       │
│ hold_reason           │           │ user_id          │
│ hold_by, hold_at      │           │ reason           │
│ is_deleted            │           │ created_at       │
│ created_at            │           └──────────────────┘
└───────────────────────┘

shipments (출고/반품/이동)
┌──────────────────────────┐
│ id                       │
│ operator_id              │
│ order_id                 │
│ client_id                │
│ shipment_type:           │
│   normal|return|transfer │
│ sku_id, quantity         │
│ location_id              │
│ from_warehouse_id        │
│ to_warehouse_id          │
│ reason                   │
│ invoice_no, status       │
│ is_deleted, created_at   │
└──────────────────────────┘
```

### 4.5 피킹/패킹 테이블

```
picking_lists                       picking_list_items
┌───────────────────────┐          ┌──────────────────────┐
│ id                    │   1:N    │ id                   │
│ operator_id           ├─────────►│ picking_list_id      │
│ list_no               │          │ order_id             │
│ list_type:            │          │ sku_id               │
│   by_order|by_product │          │ location_id          │
│   |by_location        │          │ location_code        │
│ warehouse_id          │          │ expected_qty         │
│ client_id             │          │ picked_qty           │
│ status:               │          │ lot_number           │
│   created|in_progress │          │ status:              │
│   |completed          │          │   pending|picked|    │
│ assigned_to           │          │   short              │
│ total_items           │          │ picked_at            │
│ picked_items          │          └──────────────────────┘
│ created_by            │
│ created_at            │
│ completed_at          │
└───────────────────────┘

packing_jobs (패킹 작업)
┌──────────────────────────┐
│ id                       │
│ operator_id, order_id    │
│ user_id                  │
│ scanned_barcode          │
│ channel, order_no        │
│ product_name             │
│ recipient_name           │
│ order_info (JSONB):      │
│   {items, scanned_items, │
│    materials}            │
│ status: queued|recording │
│   |completed|cancelled   │
│ video_path               │
│ video_size_bytes         │
│ video_duration_ms        │
│ started_at, completed_at │
│ is_deleted, created_at   │
└──────────────────────────┘
```

### 4.6 과금/재무 테이블

```
client_billing_logs              expenses                 monthly_pnl
┌──────────────────┐            ┌──────────────────┐    ┌──────────────┐
│ id               │            │ id               │    │ id           │
│ operator_id      │            │ operator_id      │    │ operator_id  │
│ client_id        │            │ category:        │    │ year_month   │
│ billing_type:    │            │  tax_invoice|    │    │ revenue      │
│  inbound|outbound│            │  labor|rent|     │    │ cost         │
│  |storage|return │            │  utility|...     │    │ profit       │
│  |packing        │            │ amount           │    │ detail(JSON) │
│ order_id         │            │ description      │    │ created_at   │
│ amount, quantity │            │ year_month       │    └──────────────┘
│ rate, memo       │            │ vendor_name      │
│ is_deleted       │            │ is_deleted       │
│ created_at       │            │ created_at       │
└──────────────────┘            └──────────────────┘

client_invoices                  failed_billing_events
┌──────────────────┐            ┌──────────────────┐
│ id               │            │ id               │
│ operator_id      │            │ operator_id      │
│ client_id        │            │ billing_type     │
│ year_month       │            │ client_id        │
│ total_amount     │            │ order_id         │
│ status           │            │ error_message    │
│ issued_at        │            │ payload(JSONB)   │
│ is_deleted       │            │ created_at       │
└──────────────────┘            └──────────────────┘
```

### 4.7 감사/시스템 테이블

```
audit_logs (감사 로그)
┌──────────────────────────┐
│ id                       │
│ operator_id              │
│ table_name               │
│ record_id                │
│ action: create|update|   │
│   delete|upsert|restore  │
│ before_data (JSONB)      │
│ after_data (JSONB)       │
│ user_id                  │
│ user_name                │
│ created_at               │
└──────────────────────────┘

inbound_receipts                 inventory_adjustments
┌──────────────────┐            ┌──────────────────┐
│ id               │            │ id               │
│ operator_id      │            │ operator_id      │
│ client_id        │            │ sku_id           │
│ warehouse_id     │            │ location_id      │
│ receipt_no       │            │ adjust_type:     │
│ status:          │            │  increase|decrease│
│  pending|        │            │  |write_off|     │
│  inspecting|     │            │  correction      │
│  completed|      │            │ quantity         │
│  cancelled       │            │ reason, memo     │
│ total_qty        │            │ adjusted_by      │
│ inspected_qty    │            │ is_deleted       │
│ memo             │            │ created_at       │
│ received_by      │            └──────────────────┘
│ is_deleted       │
│ created_at       │
└──────────────────┘
```

---

## 5. 아키텍처 계층도

```
┌─────────────────────────────────────────────────────────────────┐
│                       사용자 인터페이스                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌────────────────┐ │
│  │운영자포털 │ │고객사포털│ │패킹센터포털  │ │ REST API       │ │
│  │/operator │ │/client  │ │/packing      │ │ /api/v1        │ │
│  └──────────┘ └──────────┘ │  ├ 패킹작업  │ └────────────────┘ │
│                             │  ├ 피킹모드  │                    │
│                             │  └ 현장모드  │                    │
│                             │    ├입고스캔 │                    │
│                             │    ├창고이동 │                    │
│                             │    ├재고실사 │                    │
│                             │    └출고상차 │                    │
│                             └──────────────┘                    │
├─────────────────────────────────────────────────────────────────┤
│                      Flask Blueprints                           │
│  operator_bp │ client_bp │ packing_bp │ api_bp │ auth_bp       │
├─────────────────────────────────────────────────────────────────┤
│                       서비스 계층                                │
│  warehouse_service │ inventory_service │ picking_service         │
│  client_billing_service │ shipment_guard │ scan_validator        │
│  finance_service │ tz_utils                                     │
├─────────────────────────────────────────────────────────────────┤
│                     Repository 계층                              │
│  BaseRepository (CRUD + audit + soft delete + tenant filter)     │
│  ├ InventoryRepo │ WarehouseRepo │ OrderRepo │ PickingRepo      │
│  ├ PackingRepo │ ClientRepo │ UserRepo │ BillingRepo             │
│  ├ ClientBillingRepo │ ClientRateRepo │ AuditRepo │ FinanceRepo  │
│  └ ClientMarketplaceRepo                                        │
├─────────────────────────────────────────────────────────────────┤
│                    Supabase (PostgreSQL + PostgREST)             │
│  PostgreSQL 15 │ PostgREST API │ Supabase Storage               │
│  (RLS off — app-level tenant filter via operator_id)            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. DB 연결 구조

### 6.1 연결 설정 (config.py)
```python
class Config:
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')  # service_role key
```

### 6.2 연결 초기화 (app.py)
```python
# app.py → create_app()
from supabase import create_client
app.supabase = create_client(url, key)  # supabase-py Client 인스턴스
```

### 6.3 Repository 팩토리 (db_utils.py)
```python
def get_repo(name):
    """요청 컨텍스트에서 Repository 인스턴스 생성.
    Flask g.operator_id로 테넌트 자동 격리."""
    from flask import current_app, g
    repo_class = current_app.repos[name]
    return repo_class(current_app.supabase, g.operator_id)
```
- `current_app.repos` → app.py의 _init_repositories()에서 등록한 딕셔너리
- `g.operator_id` → before_request에서 current_user.operator_id로 설정

### 6.4 BaseRepository 데이터 접근 패턴 (repositories/base.py)
```python
class BaseRepository:
    def __init__(self, supabase_client, operator_id=None):
        self.client = supabase_client   # supabase-py Client
        self.operator_id = operator_id  # 테넌트 ID

    def _apply_tenant_filter(self, query):
        """모든 쿼리에 operator_id 필터 자동 적용."""
        if self.operator_id:
            query = query.eq('operator_id', self.operator_id)
        return query

    def _query(self, table, columns='*', filters=None, order_by=None, ...):
        q = self.client.table(table).select(columns)
        q = self._apply_tenant_filter(q)
        # 소프트 삭제 테이블은 is_deleted=false 자동 추가
        if table in SOFT_DELETE_TABLES:
            q = q.eq('is_deleted', False)
        for col, op, val in (filters or []):
            if op == 'eq': q = q.eq(col, val)
            elif op == 'like': q = q.like(col, val)
            elif op == 'in': q = q.in_(col, val)
            elif op == 'gte': q = q.gte(col, val)
            elif op == 'lte': q = q.lte(col, val)
            elif op == 'neq': q = q.neq(col, val)
            elif op == 'gt': q = q.gt(col, val)
            elif op == 'lt': q = q.lt(col, val)
            elif op == 'is_null': q = q.is_(col, 'null')
        return q.execute().data

    def _insert(self, table, data):
        data['operator_id'] = self.operator_id
        result = self.client.table(table).insert(data).execute()
        self._audit_log(table, result.data[0]['id'], 'create', after_data=result.data[0])
        return result.data[0]

    def _update(self, table, record_id, data):
        # 변경 전 스냅샷
        before = self.client.table(table).select('*').eq('id', record_id).execute().data
        result = self.client.table(table).update(data).eq('id', record_id).execute()
        self._audit_log(table, record_id, 'update',
                       before_data=before[0] if before else None,
                       after_data=result.data[0] if result.data else None)
        return result.data[0]

    def _delete(self, table, record_id):
        if table in SOFT_DELETE_TABLES:
            return self._update(table, record_id, {
                'is_deleted': True,
                'deleted_at': now_kst().isoformat(),
                'deleted_by': _get_current_user_name(),
            })
        else:
            return self.client.table(table).delete().eq('id', record_id).execute()

    def _upsert(self, table, data, on_conflict='id'):
        data['operator_id'] = self.operator_id
        result = self.client.table(table).upsert(data, on_conflict=on_conflict).execute()
        return result.data[0]

    def _restore(self, table, record_id):
        """소프트 삭제된 레코드 복원."""
        return self.client.table(table).update({
            'is_deleted': False, 'deleted_at': None, 'deleted_by': None
        }).eq('id', record_id).execute()
```

### 6.5 데이터 흐름 예시: 현장모드 입고 스캔

```
[모바일 브라우저] → POST /packing/api/field/inbound
    │  Request Body: { barcode: "8801234567890", location_id: 5, quantity: 10 }
    │
    ├── [packing_bp] api_field_inbound()
    │   ├── inv_repo = get_repo('inventory')
    │   │   └── InventoryRepository(app.supabase, g.operator_id=1)
    │   │
    │   ├── inv_repo.get_sku_by_barcode("8801234567890")
    │   │   → self.client.table('skus').select('*')
    │   │     .eq('operator_id', 1).eq('barcode', '8801234567890')
    │   │     .execute()
    │   │   → SQL: SELECT * FROM skus
    │   │          WHERE operator_id=1 AND barcode='8801234567890'
    │   │
    │   ├── process_inbound(inv_repo, sku_id=42, location_id=5, qty=10)
    │   │   ├── inv_repo.get_stock(42, 5)
    │   │   │   → SELECT * FROM inventory_stock
    │   │   │     WHERE sku_id=42 AND location_id=5 AND operator_id=1
    │   │   │
    │   │   ├── inv_repo.upsert_stock({sku_id:42, location_id:5, quantity:110})
    │   │   │   → INSERT INTO inventory_stock(operator_id, sku_id, location_id, quantity)
    │   │   │     VALUES(1, 42, 5, 110)
    │   │   │     ON CONFLICT(sku_id, location_id, lot_number)
    │   │   │     DO UPDATE SET quantity=110
    │   │   │   → INSERT INTO audit_logs(table_name, action, after_data, ...)
    │   │   │
    │   │   └── inv_repo.log_movement({type:'inbound', qty:10, memo:'현장스캔 입고'})
    │   │       → INSERT INTO inventory_movements(...)
    │   │       → INSERT INTO audit_logs(...)
    │   │
    │   └── Response: {ok:true, sku_name:"상품명", current_stock:110}
    │
    └── [모바일 브라우저] → playSuccess(880Hz) + 결과카드 표시
```

---

## 7. 인증 및 권한 체계

### 7.1 역할 계층

| 역할 | 레벨 | 포털 | 설명 |
|------|------|------|------|
| super_admin | 0 | operator | 플랫폼 관리자 |
| owner | 1 | operator | 운영사 대표 |
| admin | 2 | operator | 관리자 |
| manager | 3 | operator | 운영 책임자 |
| warehouse | 4 | operator | 창고 관리자 |
| cs | 5 | operator | CS 담당 |
| viewer | 6 | operator | 조회 전용 |
| client_admin | 10 | client | 고객사 관리자 |
| client_staff | 11 | client | 고객사 직원 |
| client_viewer | 12 | client | 고객사 조회 |
| packing_lead | 20 | packing | 패킹 리더 |
| packing_worker | 21 | packing | 패킹 작업자 |

### 7.2 페이지 접근 제어
```python
PAGE_REGISTRY = {
    'endpoint': {'label': '...', 'portal': 'operator', 'min_role': 'warehouse'},
}
# user_role_level <= min_role_level → 접근 허용
```

### 7.3 포털 자동 라우팅
```
로그인 성공
  └→ user.get_portal() → 'operator' | 'client' | 'packing'
      └→ redirect(url_for(f'{portal}.dashboard'))
```

---

## 8. 현장모드 상세 구조

### 8.1 현장모드 API 엔드포인트

| URL | Method | 기능 | 요청 | 응답 |
|-----|--------|------|------|------|
| `/packing/field` | GET | 대시보드 (오늘 작업현황) | — | HTML |
| `/packing/field/inbound` | GET | 입고 스캔 화면 | — | HTML |
| `/packing/api/field/inbound` | POST | 입고 처리 | {barcode, location_id, quantity, lot_number} | {ok, sku_name, current_stock} |
| `/packing/field/transfer` | GET | 창고이동 화면 | — | HTML |
| `/packing/api/field/transfer` | POST | 이동 처리 | {barcode, from_location_id, to_location_id, quantity} | {ok, sku_name, quantity} |
| `/packing/field/stockcheck` | GET | 재고실사 화면 | — | HTML |
| `/packing/api/field/stock-at-location` | POST | 로케이션 재고 조회 | {location_id} | {ok, items[]} |
| `/packing/api/field/stockcheck` | POST | 실사 조정 반영 | {location_id, adjustments[]} | {ok, adjusted_count} |
| `/packing/field/shipping` | GET | 출고상차 화면 | — | HTML |
| `/packing/api/field/shipping-scan` | POST | 상차 스캔 | {barcode} | {ok, order_no, recipient} |
| `/packing/api/field/sku-lookup` | POST | SKU+재고 조회 | {barcode, location_id?} | {ok, sku_*, stock_qty, total_stock} |

### 8.2 현장모드 UI 패턴

| 패턴 | 구현 |
|------|------|
| 바코드 입력 | `<input class="scan-input-lg">` + Enter 이벤트 |
| 자동 포커스 | `document.addEventListener('click')` → input.focus() |
| 성공 피드백 | AudioContext 880Hz sine 0.12s + 녹색 결과카드 (4초) |
| 실패 피드백 | AudioContext 300Hz square 0.3s + 빨간 배너 (3초) |
| 세션 이력 | 클라이언트 배열 + DOM 실시간 렌더링 |
| 연속 스캔 | 처리 후 input.value='' + focus() |
| 로케이션 표시 | 3단계 경로: "창고 > 구역 > A-01-01" |

### 8.3 기존 기능 재활용 매핑

| 기존 모듈 | 재활용 내역 |
|-----------|-----------|
| scan_validator.py | sku-lookup API에서 바코드→SKU 조회 로직 재사용 |
| warehouse_service.py | process_inbound() 함수 직접 호출 (입고) |
| inventory_repo.py | adjust_stock(), log_movement() 직접 호출 (이동/실사) |
| warehouse_repo.py | list_all_locations_with_path() (로케이션 목록) |
| picking.html | 880Hz/300Hz 오디오 패턴, scan-input-lg CSS |
| recording.html | 자동 포커스 패턴, 에러 배너 패턴 |

---

## 9. 소프트 삭제 대상 테이블 (13개)

```python
SOFT_DELETE_TABLES = {
    'skus', 'clients', 'warehouses', 'users',
    'orders', 'shipments', 'packing_jobs',
    'inbound_receipts', 'inventory_adjustments',
    'client_billing_logs', 'client_invoices',
    'picking_lists', 'expenses',
}
```

삭제 시: `is_deleted=True, deleted_at=KST시각, deleted_by=사용자명`
조회 시: `_query()`에서 자동 `is_deleted=false` 필터 (해당 테이블만)

---

## 10. 2-Phase Inventory Commit

```
주문확정 (confirmed)
  └→ reserve_stock()
      ├─ FIFO 순서로 재고 탐색 (expiry_date ASC)
      ├─ inventory_stock.reserved_qty += 수량
      ├─ inventory_reservations INSERT (status='reserved')
      └─ 실패 시 전체 롤백

패킹완료 (packed)
  └→ commit_stock()
      ├─ inventory_stock.reserved_qty -= 수량
      ├─ inventory_stock.quantity -= 수량
      ├─ inventory_movements INSERT (type='outbound')
      └─ inventory_reservations UPDATE (status='committed')

주문취소 (cancelled)
  └→ release_stock()
      ├─ inventory_stock.reserved_qty -= 수량
      └─ inventory_reservations UPDATE (status='released')
```

---

## 11. 과금 체계

### 건별 과금 (client_billing_logs)
| 과금유형 | 트리거 시점 | 단가 소스 |
|---------|-----------|----------|
| inbound | 입고 완료 시 | client_rates.inbound_fee_per_unit |
| outbound | 출고 확정 시 | client_rates.outbound_fee_per_order |
| packing | 패킹 완료 시 | client_rates.packing_fee + 부자재비 |
| return | 반품 처리 시 | client_rates.return_fee_per_unit |
| storage | 일별 스냅샷 | client_rates.storage_fee_per_unit_day |

### P&L 계산 (finance_service.py)
```
Revenue = SUM(client_billing_logs.amount) WHERE year_month = target
Cost = SUM(expenses.amount) WHERE year_month = target
Profit = Revenue - Cost
```

비용 카테고리 9종: tax_invoice, labor, rent, utility, supplies, delivery, insurance, depreciation, etc

---

## 12. 마이그레이션 이력

| # | 주요 내용 |
|---|----------|
| 001 | 초기: operators, users, clients, warehouses, zones, locations |
| 002 | skus, inventory_stock, inventory_movements |
| 003 | orders, order_items, shipments |
| 004 | picking_lists, picking_list_items, inventory_reservations, packing_jobs |
| 005-010 | 과금, 마켓플레이스, 상태로그, 최소재고 등 |
| 011 | dedupe_key (중복방지) |
| 012 | daily_inventory_snapshots |
| 013 | marketplace_connect |
| 014 | audit_logs, inbound_receipts, inventory_adjustments, expenses, monthly_pnl, 소프트삭제 13개 |
| 015 | shipments: shipment_type, client_id, sku_id, from/to_warehouse_id 등 추가 |

---

## 13. 운영 포털 구조

| 포털 | URL | 대상 | 주요 기능 |
|------|-----|------|----------|
| Operator | /operator/* | 운영사 | 주문/재고/피킹/출고/과금/분석/설정 |
| Client | /client/* | 고객사 | 재고조회/주문현황/영상/과금내역 |
| Packing | /packing/* | 작업자 | 패킹/피킹/촬영/현장모드 |
| API | /api/v1/* | 외부 | 토큰인증 REST API |

### 메뉴 그룹 (packing 포털)
```
현장모드  → 현장홈, 입고스캔, 창고이동, 재고실사, 출고상차
패킹     → 작업현황, 피킹모드, 촬영모드, 작업큐, 바코드스캔, 실적조회
```

---

## 14. 향후 확장 방향

1. **카메라 바코드 스캔**: html5-qrcode 라이브러리 연동 (BT 스캐너 없이도 사용)
2. **TTS 음성 안내**: 현장모드에서 `speak()` 함수 적용
3. **WebSocket 실시간 동기화**: 관리자↔현장 작업 상태 실시간 알림
4. **PWA**: 오프라인 캐싱, 푸시 알림, 홈 화면 추가
5. **택배 API 연동**: CJ대한통운/한진 송장 자동 등록
6. **AI 이상탐지**: 재고 불일치 자동 감지, 작업 패턴 분석

---

*이 문서는 PackFlow 시스템의 2026-03-18 기준 구현 상태를 반영합니다.*
