# 3PL SaaS 시스템 아키텍처 계획서

> 작성일: 2026-03-14
> 목적: 3PL 물류대행 SaaS 제품 구조 설계 및 검토
> 상태: 초안 (GPT/Gemini 검토용)

---

## 1. 제품 비전 및 분할 전략

### 1.1 3개 제품 라인업

| 제품 | 타겟 | 핵심 가치 |
|------|------|-----------|
| **3PL 물류대행 SaaS** | 풀필먼트/3PL 업체 | 다중 고객사 재고·출고·정산 통합 관리 |
| **온라인 자동접수/정산** | 온라인 셀러 | 멀티채널 주문수집·송장·정산 자동화 |
| **식품 전용 ERP** | 식품 제조/유통사 | 생산·재고·유통기한·원가 관리 |

### 1.2 현재 autotool과의 관계

```
현재 autotool (모놀리식)
├── 주문/출고/송장 → 3PL SaaS + 온라인자동접수
├── 재고/입고/생산 → 3PL SaaS + 식품ERP
├── 회계/세금계산서  → 공통 모듈 (각 제품에서 선택적 사용)
└── 마켓플레이스 API → 온라인자동접수 (핵심) + 3PL SaaS (연동)
```

---

## 2. 3PL SaaS 시스템 설계

### 2.1 3개 포털 구조

```
┌─────────────────────────────────────────────────────────┐
│                    3PL SaaS Platform                     │
├─────────────────┬──────────────────┬────────────────────┤
│  ① 3PL 관리자   │  ② 고객사 포털   │  ③ 패킹센터 포털  │
│   (운영사)       │  (위탁 고객사)    │  (현장 작업자)     │
├─────────────────┼──────────────────┼────────────────────┤
│ - 전체 고객 관리  │ - 내 재고 조회    │ - 피킹 리스트      │
│ - 전체 재고 현황  │ - 내 주문 현황    │ - 패킹 작업        │
│ - 정산/매출 관리  │ - 입고 요청       │ - 송장 출력        │
│ - 창고/구역 설정  │ - 출고 요청       │ - 검수 처리        │
│ - 요금 체계 설정  │ - 정산 내역       │ - 영상 녹화        │
│ - 계약 관리      │ - 영상 다운로드   │ - 바코드 스캔      │
│ - 리포트/분석    │ - 발주 추천 확인  │ - 실시간 작업현황  │
│ - 채널 연동 설정  │ - 채널별 주문현황 │ - 다중 작업자 동시 │
└─────────────────┴──────────────────┴────────────────────┘
```

### 2.2 사용자 역할 (Role) 체계

```
3PL 운영사 (Operator)
├── owner       — 3PL 회사 대표/최고관리자
├── admin       — 시스템 관리자
├── manager     — 운영 책임자
├── warehouse   — 창고 관리자
├── cs          — 고객 응대/CS
└── viewer      — 조회 전용

고객사 (Client)
├── client_admin   — 고객사 관리자
├── client_staff   — 고객사 직원
└── client_viewer  — 고객사 조회 전용

패킹센터 (Packing)
├── packing_lead   — 패킹 리더
└── packing_worker — 패킹 작업자
```

---

## 3. 멀티테넌시 아키텍처

### 3.1 현재 vs 목표

```
현재 autotool:
  Session 기반 DB 전환 (db_pool에 2개 사업체)
  → 단순하지만 확장성 한계

목표 3PL SaaS:
  Tenant 계층 구조 필요
  → 3PL 운영사 (Operator) > 고객사 (Client) > 채널/창고
```

### 3.2 테넌트 격리 전략 비교

| 전략 | 설명 | 장점 | 단점 |
|------|------|------|------|
| **A. DB-per-Tenant** | 3PL 운영사마다 별도 Supabase 프로젝트 | 완전 격리, 보안 최상 | 관리 복잡, 비용 높음 |
| **B. Schema-per-Tenant** | 하나의 DB, 운영사마다 별도 스키마 | 격리 + 관리 균형 | Supabase에서 스키마 분리 제한적 |
| **C. Row-Level Security** | 하나의 DB, operator_id 컬럼으로 분리 | 관리 쉬움, 비용 낮음 | 격리 수준 낮음, 쿼리마다 필터 필요 |
| **D. 하이브리드** | 기본은 RLS, 대형 고객은 별도 DB | 유연성 최대 | 구현 복잡도 높음 |

### 3.3 권장: 하이브리드 (D안)

```
Phase 1 (MVP): Row-Level Security (C안)
  - 빠른 개발, 낮은 비용
  - operator_id + client_id 컬럼으로 격리
  - Supabase RLS 정책 활용

Phase 2 (성장기): 하이브리드 (D안)
  - 대형 운영사 → 별도 Supabase 프로젝트
  - 소형 운영사 → 공유 DB + RLS
  - 현재 autotool의 db_pool 패턴 확장
```

### 3.4 데이터 계층 구조

```
Platform (SaaS 전체)
└── Operator (3PL 운영사) ← tenant 경계
    ├── Warehouses (창고들)
    │   └── Zones (구역들)
    │       └── Locations (위치/선반)
    ├── Clients (고객사들)
    │   ├── Products (고객사별 제품)
    │   ├── Channels (판매 채널)
    │   └── Orders (주문)
    ├── Inventory (재고 - 창고×고객사×제품)
    ├── Workers (패킹센터 작업자)
    └── Billing (정산/요금)
```

---

## 4. 핵심 모듈 설계

### 4.1 창고/구역 관리 (Warehouse Management)

```
warehouses
├── id, operator_id, name, address, type
├── is_active, capacity_info
└── metadata (온도관리여부, 특수시설 등)

warehouse_zones
├── id, warehouse_id, zone_code, zone_name
├── zone_type (상온/냉장/냉동/위험물)
├── capacity, current_usage
└── location_format (A-01-01 같은 위치체계)

warehouse_locations
├── id, zone_id, location_code
├── location_type (랙/팔레트/벌크)
├── is_occupied, current_product_id
└── max_quantity
```

**핵심 기능:**
- 창고별 구역 트리 관리 (창고 > 구역 > 위치)
- 위치 코드 체계 설정 (예: A동-1열-3단)
- 구역별 보관 조건 설정 (온도, 습도)
- 실시간 적재율 시각화
- 최적 입고 위치 추천

### 4.2 다중 고객사 재고 관리

```
client_inventory
├── id, operator_id, client_id
├── product_id, warehouse_id, zone_id, location_id
├── quantity, available_qty, reserved_qty, damaged_qty
├── lot_number, expiry_date
├── inbound_date, last_movement_date
└── unit_cost (원가 — 정산용)

inventory_movements
├── id, inventory_id, movement_type
│   (INBOUND/OUTBOUND/TRANSFER/ADJUST/RETURN)
├── quantity, before_qty, after_qty
├── reference_type, reference_id (주문번호, 입고번호 등)
├── worker_id, processed_at
└── note
```

**핵심 차별점 (기존 autotool 대비):**
- **고객사별 분리**: 같은 창고에 A사, B사 제품이 있어도 완전 분리
- **위치 추적**: 어떤 제품이 어떤 선반에 있는지 정확히
- **실시간 차감**: 출고 시 즉시 재고 반영 (WebSocket)
- **LOT/유통기한**: 선입선출(FIFO) 자동 적용
- **가용재고 분리**: 총재고 - 예약수량 = 가용재고

### 4.3 주문 처리 파이프라인

```
주문 흐름:

  [채널 주문수집] → [주문 풀] → [검수/매칭] → [피킹지시]
       │                │            │             │
  자동 API수집      고객사별 분류    채널 검증     피킹리스트 생성
  엑셀 업로드       중복 체크       상품 매핑     구역별 최적 경로
  수동 등록         합배송 처리     재고 확인     작업자 배정
                                                    │
  [발송완료] ← [송장출력] ← [패킹/검수] ← [피킹완료]
       │            │            │             │
  채널 송장전송   택배사 API    영상 녹화      수량 확인
  상태 업데이트   운송장 발행   무게 체크      바코드 스캔
  재고 차감       라벨 출력    파손 검수
```

**멀티채널 지원 (확장 필요 영역):**

```
현재 지원:          추가 검토 대상:
├── 네이버 스마트스토어  ├── 11번가
├── 쿠팡               ├── G마켓/옥션 (ESM)
├── Cafe24             ├── 위메프
└── (직접입력/엑셀)     ├── 티몬
                       ├── 인터파크
                       ├── 카카오쇼핑
                       ├── 톡스토어
                       └── 자사몰 (Shopify, 고도몰 등)
```

**채널별 고려사항:**
- 각 채널의 주문 필드 매핑 (상품명, 옵션, 수량 포맷이 다름)
- 채널별 송장 전송 API 차이
- 채널별 반품/교환 프로세스 차이
- 묶음배송/분할배송 처리 기준
- → **채널 어댑터 패턴** 필요 (현재 marketplace/ 구조 확장)

### 4.4 발주 추천 시스템

```
기존: 생산추천 (판매량 기반 생산계획)
변환: 발주추천 (재고소진 예측 기반 고객사 발주 유도)

발주 추천 로직:
1. 일평균 출고량 계산 (최근 7/14/30일)
2. 현재 가용재고 ÷ 일평균 출고량 = 잔여일수
3. 리드타임(입고 소요일) 고려
4. 안전재고 수준 설정
5. 잔여일수 < 리드타임 + 안전재고일 → 발주 알림

자동 발주 유도:
├── 대시보드 알림 (고객사 포털)
├── 이메일/카카오 알림톡 발송
├── 자동 발주서 생성 (승인만 하면 됨)
└── 이력 기반 추천 수량 제안
```

### 4.5 영상 관리 (기존 패킹센터 보강)

```
현재 구현 완료 (packing.py — 954줄):
├── MediaRecorder API (WebM/VP8) + 바코드 스캔 연동
├── Supabase Storage 업로드 (packing-videos 버킷)
│   └── 경로: YYYY/MM/DD/{user_id}_{barcode}_{timestamp}.webm
├── packing_jobs 테이블 (상태관리, 영상경로, 파일크기)
├── Signed URL 발급 (1시간 만료)
└── 택배사 API 연동 (CJ대한통운) + 재고 차감

3PL SaaS 전환 시 보강 사항:
├── operator_id / client_id 컬럼 추가 → 고객사별 분리
├── 고객사 포털에서 본인 주문 영상만 조회/다운로드
├── 보관기간 정책 (고객사별 설정 가능, 기본 30일)
├── 자동 삭제 배치 (expires_at 기반)
└── 스토리지 버킷 분리 (operator별 또는 prefix 분리)
```

**핵심: 대부분 기존 코드 재사용. 멀티테넌트 필터만 추가.**

### 4.6 비용 청구 시스템 (Billing)

3PL 운영사가 고객사에 청구하는 물류 대행 비용 전체를 관리.

```
비용 항목 체계:

┌─────────────────────────────────────────────────────────────┐
│                    비용 청구 카테고리                          │
├─────────────┬───────────────────┬───────────────────────────┤
│  출고 비용   │   보관 비용        │   부가 비용               │
├─────────────┼───────────────────┼───────────────────────────┤
│ 기본 포장비  │ 창고 보관료        │ 부자재비                  │
│  (건당)      │  (CBM/일 또는     │  (박스, 에어캡, 테이프 등)│
│             │   팔레트/일)       │                           │
│ 합포장비    │ 냉장/냉동 할증     │ 라벨/스티커 비용          │
│  (2개이상   │                   │                           │
│   합배송)   │ 구역별 단가 차등   │ 반품 처리비               │
│             │                   │                           │
│ 피킹비      │ 장기보관 할증      │ 입고 검수비               │
│  (SKU당)    │  (60일 초과 등)   │                           │
│             │                   │ 특수 포장비               │
│ 송장 출력비  │                   │  (냉장팩, 아이스박스 등)  │
│             │                   │                           │
│ 택배비 대행  │                   │ 사진/영상 촬영비          │
│  (실비+수수료│                   │                           │
│   또는 정액) │                   │ 기타 부대비용             │
└─────────────┴───────────────────┴───────────────────────────┘
```

**요금 체계 설계:**

```
1. 기본 요금 (operator 전체 기본값)
   └── 고객사별 개별 요금 (우선 적용)
       └── 기간별 단가 (계약 갱신 시 변경)

2. 계산 방식별 분류:
   ├── 건당 (per_order): 포장비, 합포장비, 반품처리비
   ├── 개당 (per_unit): 피킹비, 입고검수비
   ├── 일당 (per_day): 보관료 (CBM 또는 팔레트 기준)
   ├── 실비 (actual): 부자재비, 택배비
   └── 월정액 (monthly): 시스템 이용료, 기본 보관료

3. 합포장 요금 계산 예시:
   ├── 단일 주문 (1건 1박스) → 기본 포장비 1,000원
   ├── 합포장 (2건 1박스)   → 합포장비 1,500원 (건당 750원)
   ├── 합포장 (3건 1박스)   → 합포장비 2,000원
   └── 고객사별 합포장 요율 별도 설정 가능

4. 창고 보관료 계산:
   ├── 기준: CBM(부피) 또는 팔레트 수 또는 SKU당
   ├── 일할 계산: (재고수량 × 단위부피 × 일단가) × 보관일수
   ├── 구역별 차등: 상온 < 냉장 < 냉동
   ├── 장기보관 할증: 60일 초과분 × 1.5배, 90일 초과 × 2배
   └── 월말 일괄 계산 또는 실시간 누적
```

**청구 플로우:**

```
[자동 집계] → [청구서 생성] → [고객사 확인] → [청구 확정] → [수금 관리]
     │              │              │              │              │
 매일/주/월      운영사 검토    고객사 포털     세금계산서     입금 확인
 자동 계산       수동 조정      이의제기 가능    발행 연동      미수금 추적
 건별 기록       항목 추가/삭제  승인/반려       (홈택스 연동)  자동 매칭
```

**고객사 포털 — 비용 화면:**

```
┌─────────────────────────────────────────────┐
│  📊 2026년 3월 비용 내역                     │
├──────────────────┬──────────┬───────────────┤
│ 항목             │ 수량     │ 금액          │
├──────────────────┼──────────┼───────────────┤
│ 기본 포장비      │ 1,234건  │   1,234,000원 │
│ 합포장비         │   156건  │     234,000원 │
│ 피킹비 (SKU기준) │ 2,891개  │     578,200원 │
│ 창고 보관료(상온)│ 12.5CBM  │     375,000원 │
│ 창고 보관료(냉장)│  3.2CBM  │     192,000원 │
│ 부자재비         │   실비   │     156,800원 │
│ 택배비 대행      │ 1,234건  │   3,702,000원 │
│ 반품 처리비      │    23건  │      46,000원 │
├──────────────────┼──────────┼───────────────┤
│ 합계             │          │   6,518,000원 │
│ 부가세           │          │     651,800원 │
│ 청구 총액        │          │   7,169,800원 │
└──────────────────┴──────────┴───────────────┘
│ [상세 내역 다운로드(엑셀)]  [이의제기]  [승인] │
└─────────────────────────────────────────────┘
```

---

## 5. 기술 아키텍처

### 5.1 현재 스택 유지 vs 변경

```
유지 (검증됨):              변경/추가 검토:
├── Flask (백엔드)           ├── FastAPI (비동기 처리 — WebSocket용)
├── Supabase (DB/Auth)       ├── Redis (캐싱, 실시간 재고)
├── Jinja2 (템플릿)          ├── WebSocket (실시간 업데이트)
├── Bootstrap (UI)           ├── Celery (비동기 작업큐)
└── 기존 서비스 패턴         ├── S3/Cloud Storage (영상)
                             └── 프론트엔드 분리 (Vue/React — 장기)
```

### 5.2 추천 아키텍처 (Phase별)

**Phase 1 — MVP (Flask 유지, 빠른 출시)**

```
┌──────────────────────────────────────┐
│           Flask Application          │
│  ┌──────────┐  ┌──────────────────┐  │
│  │ Blueprint│  │ Blueprint        │  │
│  │ (관리자) │  │ (고객사/패킹)    │  │
│  └────┬─────┘  └───────┬──────────┘  │
│       └────────┬───────┘             │
│          Service Layer               │
│       (기존 패턴 + tenant 필터)      │
├──────────────────────────────────────┤
│     Supabase (RLS + tenant 격리)     │
│     Supabase Storage (영상 파일)     │
└──────────────────────────────────────┘
```

**Phase 2 — 확장 (실시간 + 비동기)**

```
┌───────────┐    ┌───────────┐    ┌────────────┐
│ Flask App │    │ WebSocket │    │ Celery     │
│ (HTTP API)│    │ Server    │    │ Workers    │
│           │    │ (실시간)  │    │ (비동기)   │
└─────┬─────┘    └─────┬─────┘    └──────┬─────┘
      │                │                  │
      └────────────────┼──────────────────┘
                       │
              ┌────────┴────────┐
              │    Redis        │
              │ (캐시+메시지큐) │
              └────────┬────────┘
                       │
              ┌────────┴────────┐
              │   Supabase      │
              │ (DB + Storage)  │
              └─────────────────┘
```

### 5.3 URL/라우팅 구조

```
3PL 관리자 포털:
  /operator/dashboard
  /operator/clients
  /operator/warehouses
  /operator/inventory
  /operator/orders
  /operator/billing
  /operator/reports
  /operator/settings

고객사 포털:
  /client/dashboard
  /client/inventory
  /client/orders
  /client/inbound
  /client/billing
  /client/videos
  /client/reorder

패킹센터 포털:
  /packing/dashboard
  /packing/picking
  /packing/packing
  /packing/shipping
  /packing/scan
```

### 5.4 인증/인가 구조

```
현재:
  Flask-Login + session + role_required

3PL SaaS:
  ┌─────────────────────────────┐
  │       인증 (Authentication)  │
  │  Supabase Auth              │
  │  + 소셜 로그인 (카카오 등)  │
  │  + 이메일/비밀번호           │
  └──────────┬──────────────────┘
             │
  ┌──────────┴──────────────────┐
  │       인가 (Authorization)   │
  │                              │
  │  Level 1: Portal 분리        │
  │    → URL prefix로 포털 결정  │
  │                              │
  │  Level 2: Tenant 격리        │
  │    → operator_id 기반 필터   │
  │                              │
  │  Level 3: Role 기반 접근     │
  │    → 기존 role_required 확장 │
  │                              │
  │  Level 4: Data 수준 필터     │
  │    → 고객사는 자기 데이터만  │
  └─────────────────────────────┘
```

---

## 6. 데이터베이스 설계 (핵심 테이블)

### 6.1 플랫폼/테넌트 관리

```sql
-- 3PL 운영사 (테넌트)
CREATE TABLE operators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name TEXT NOT NULL,
    business_number TEXT,          -- 사업자등록번호
    plan_type TEXT DEFAULT 'basic', -- basic/pro/enterprise
    max_clients INT DEFAULT 10,
    max_warehouses INT DEFAULT 3,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    settings JSONB DEFAULT '{}'    -- 운영사별 설정
);

-- 3PL 고객사 (위탁사)
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id UUID REFERENCES operators(id),
    company_name TEXT NOT NULL,
    contact_name TEXT,
    contact_phone TEXT,
    contact_email TEXT,
    contract_start DATE,
    contract_end DATE,
    billing_type TEXT DEFAULT 'per_order', -- per_order/monthly/custom
    is_active BOOLEAN DEFAULT TRUE,
    settings JSONB DEFAULT '{}'
);

-- 사용자 계정 (모든 포털 공용)
CREATE TABLE platform_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    name TEXT NOT NULL,
    phone TEXT,
    operator_id UUID REFERENCES operators(id),
    client_id UUID REFERENCES clients(id),  -- NULL이면 운영사 소속
    role TEXT NOT NULL,
    portal_access TEXT[] DEFAULT '{}',  -- ['operator','client','packing']
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMPTZ
);
```

### 6.2 창고/재고

```sql
-- 창고
CREATE TABLE warehouses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id UUID REFERENCES operators(id),
    name TEXT NOT NULL,
    address TEXT,
    warehouse_type TEXT DEFAULT 'ambient', -- ambient/cold/frozen/mixed
    is_active BOOLEAN DEFAULT TRUE,
    settings JSONB DEFAULT '{}'
);

-- 구역
CREATE TABLE warehouse_zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    warehouse_id UUID REFERENCES warehouses(id),
    zone_code TEXT NOT NULL,
    zone_name TEXT,
    zone_type TEXT DEFAULT 'ambient',
    total_locations INT DEFAULT 0,
    settings JSONB DEFAULT '{}'
);

-- 위치 (선반/랙)
CREATE TABLE warehouse_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id UUID REFERENCES warehouse_zones(id),
    location_code TEXT NOT NULL,      -- 예: A-01-03
    location_type TEXT DEFAULT 'rack', -- rack/pallet/bulk/floor
    max_capacity NUMERIC,
    is_occupied BOOLEAN DEFAULT FALSE,
    current_product_id UUID
);

-- 고객사별 상품 마스터
CREATE TABLE client_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id UUID REFERENCES operators(id),
    client_id UUID REFERENCES clients(id),
    sku TEXT NOT NULL,
    barcode TEXT,
    product_name TEXT NOT NULL,
    product_name_short TEXT,
    category TEXT,
    unit TEXT DEFAULT 'EA',
    weight NUMERIC,
    dimensions JSONB,                 -- {width, height, depth}
    storage_type TEXT DEFAULT 'ambient',
    expiry_management BOOLEAN DEFAULT FALSE,
    min_stock_qty INT DEFAULT 0,      -- 안전재고
    reorder_point INT DEFAULT 0,      -- 발주점
    reorder_qty INT DEFAULT 0,        -- 발주추천수량
    lead_time_days INT DEFAULT 3,     -- 입고 리드타임
    is_active BOOLEAN DEFAULT TRUE,
    channel_mappings JSONB DEFAULT '{}' -- 채널별 상품코드 매핑
);

-- 재고 (핵심 — 고객사×제품×창고×위치 단위)
CREATE TABLE inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id UUID REFERENCES operators(id),
    client_id UUID REFERENCES clients(id),
    product_id UUID REFERENCES client_products(id),
    warehouse_id UUID REFERENCES warehouses(id),
    zone_id UUID REFERENCES warehouse_zones(id),
    location_id UUID REFERENCES warehouse_locations(id),
    lot_number TEXT,
    expiry_date DATE,
    quantity INT DEFAULT 0,           -- 실재고
    available_qty INT DEFAULT 0,      -- 가용재고 (실재고 - 예약)
    reserved_qty INT DEFAULT 0,       -- 예약수량 (출고 대기)
    damaged_qty INT DEFAULT 0,        -- 파손수량
    unit_cost NUMERIC,
    last_movement_at TIMESTAMPTZ,
    UNIQUE(operator_id, client_id, product_id, warehouse_id, location_id, lot_number)
);

-- 재고 이동 이력
CREATE TABLE inventory_movements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id UUID REFERENCES operators(id),
    inventory_id UUID REFERENCES inventory(id),
    movement_type TEXT NOT NULL,       -- INBOUND/OUTBOUND/TRANSFER/ADJUST/RETURN
    quantity INT NOT NULL,
    before_qty INT,
    after_qty INT,
    reference_type TEXT,              -- ORDER/INBOUND_REQUEST/MANUAL
    reference_id TEXT,
    worker_id UUID,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 6.3 주문/출고

```sql
-- 주문
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id UUID REFERENCES operators(id),
    client_id UUID REFERENCES clients(id),
    channel TEXT,                      -- naver/coupang/cafe24/manual/excel
    channel_order_id TEXT,             -- 채널 원본 주문번호
    order_number TEXT UNIQUE,          -- 내부 주문번호
    order_date TIMESTAMPTZ,
    status TEXT DEFAULT 'received',
    -- received → confirmed → picking → packing → shipped → delivered

    -- 수령인 정보
    recipient_name TEXT,
    recipient_phone TEXT,
    recipient_address TEXT,
    recipient_zipcode TEXT,
    delivery_message TEXT,

    -- 배송 정보
    courier_code TEXT,
    tracking_number TEXT,

    -- 금액
    total_amount NUMERIC,
    shipping_fee NUMERIC,

    -- 메타
    items JSONB,                      -- [{product_id, sku, name, qty, price}]
    raw_data JSONB,                   -- 채널 원본 데이터
    created_at TIMESTAMPTZ DEFAULT NOW(),
    shipped_at TIMESTAMPTZ,

    -- 영상
    packing_video_id UUID
);

-- 입고 요청
CREATE TABLE inbound_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id UUID REFERENCES operators(id),
    client_id UUID REFERENCES clients(id),
    request_number TEXT UNIQUE,
    status TEXT DEFAULT 'requested',
    -- requested → approved → receiving → completed
    warehouse_id UUID REFERENCES warehouses(id),
    expected_date DATE,
    items JSONB,                      -- [{product_id, sku, expected_qty}]
    received_items JSONB,             -- [{product_id, actual_qty, location_id, lot, expiry}]
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
```

### 6.4 비용 청구 시스템 (Billing — 대폭 확장)

```sql
-- ============================================
-- 요금 단가 테이블 (기본값 + 고객사별 개별 단가)
-- ============================================
CREATE TABLE billing_rate_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id UUID REFERENCES operators(id),
    client_id UUID,                        -- NULL = 기본 단가, 값 있으면 고객사 개별 단가
    category TEXT NOT NULL,                -- fulfillment / storage / material / extra
    rate_code TEXT NOT NULL,               -- 아래 상세 코드
    rate_name TEXT NOT NULL,               -- 표시명
    calc_method TEXT NOT NULL,             -- per_order / per_unit / per_day / per_cbm / actual / monthly
    unit_price NUMERIC NOT NULL DEFAULT 0,
    currency TEXT DEFAULT 'KRW',
    -- 조건부 단가 (수량 구간별)
    tier_pricing JSONB,                    -- [{min_qty, max_qty, price}] 구간별 단가
    -- 할증 조건
    surcharge_rules JSONB,                 -- [{condition, multiplier, description}]
    effective_from DATE NOT NULL,
    effective_to DATE,                     -- NULL = 무기한
    is_active BOOLEAN DEFAULT TRUE,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- rate_code 상세:
-- [fulfillment] 출고 관련
--   packing_basic      기본 포장비 (건당)
--   packing_combined    합포장비 (2건 이상 합배송/건당)
--   picking_per_sku     피킹비 (SKU당)
--   picking_per_unit    피킹비 (개당)
--   invoice_print       송장 출력비 (건당)
--   shipping_handling   출고 수수료 (건당)
--   courier_fee         택배비 대행 (실비 또는 정액)
--   return_processing   반품 처리비 (건당)
--
-- [storage] 보관 관련
--   storage_ambient     상온 보관료 (CBM/일 또는 팔레트/일)
--   storage_cold        냉장 보관료
--   storage_frozen      냉동 보관료
--   storage_longterm    장기보관 할증 (60일/90일 초과)
--
-- [material] 부자재
--   box_small           소형 박스
--   box_medium          중형 박스
--   box_large           대형 박스
--   aircap              에어캡/버블랩
--   tape                테이프
--   ice_pack            아이스팩
--   ice_box             아이스박스 (냉장용)
--   label_sticker       라벨/스티커
--   custom_material     기타 부자재 (고객사 지정)
--
-- [extra] 부가
--   inbound_inspect     입고 검수비 (건당 또는 개당)
--   special_packing     특수 포장비
--   photo_service       사진 촬영비
--   video_service       영상 촬영비
--   monthly_system      월 시스템 이용료
--   custom_fee          기타 비용

-- ============================================
-- 비용 발생 건별 기록 (트랜잭션 로그)
-- ============================================
CREATE TABLE billing_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id UUID REFERENCES operators(id),
    client_id UUID REFERENCES clients(id),
    rate_code TEXT NOT NULL,
    category TEXT NOT NULL,
    -- 참조 (어떤 주문/입고에서 발생했는지)
    reference_type TEXT,               -- order / inbound / inventory / manual
    reference_id UUID,                 -- 주문ID, 입고ID 등
    reference_number TEXT,             -- 주문번호 (사람이 읽는 번호)
    -- 비용 계산
    quantity NUMERIC NOT NULL DEFAULT 1,
    unit_price NUMERIC NOT NULL,
    surcharge_amount NUMERIC DEFAULT 0,  -- 할증 금액
    total_amount NUMERIC NOT NULL,
    -- 메타
    description TEXT,                  -- "주문#1234 합포장(3건)" 등
    calc_detail JSONB,                 -- 계산 상세 근거
    billing_date DATE NOT NULL,        -- 비용 발생일
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- 월별 청구서 (고객사별)
-- ============================================
CREATE TABLE billing_invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id UUID REFERENCES operators(id),
    client_id UUID REFERENCES clients(id),
    invoice_number TEXT UNIQUE,         -- 청구서 번호 (INV-2026-03-001)
    billing_month TEXT NOT NULL,        -- '2026-03'
    -- 카테고리별 소계
    fulfillment_total NUMERIC DEFAULT 0,  -- 출고비용 소계
    storage_total NUMERIC DEFAULT 0,      -- 보관비용 소계
    material_total NUMERIC DEFAULT 0,     -- 부자재비 소계
    extra_total NUMERIC DEFAULT 0,        -- 부가비용 소계
    -- 합계
    subtotal NUMERIC DEFAULT 0,           -- 공급가액
    tax_amount NUMERIC DEFAULT 0,         -- 부가세 (10%)
    total_amount NUMERIC DEFAULT 0,       -- 청구 총액
    -- 조정
    adjustment_amount NUMERIC DEFAULT 0,  -- 수동 조정 (할인/추가)
    adjustment_note TEXT,
    -- 상태
    status TEXT DEFAULT 'draft',
    -- draft → calculated → sent → confirmed → invoiced → paid → overdue
    -- 타임라인
    calculated_at TIMESTAMPTZ,    -- 자동 집계 완료
    sent_at TIMESTAMPTZ,          -- 고객사에 전송
    confirmed_at TIMESTAMPTZ,     -- 고객사 확인/승인
    invoiced_at TIMESTAMPTZ,      -- 세금계산서 발행
    paid_at TIMESTAMPTZ,          -- 입금 확인
    due_date DATE,                -- 납부 기한
    -- 메타
    line_items JSONB,             -- 항목별 상세 [{rate_code, name, qty, price, total}]
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- 부자재 사용 기록 (실비 청구용)
-- ============================================
CREATE TABLE material_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id UUID REFERENCES operators(id),
    client_id UUID REFERENCES clients(id),
    order_id UUID,                     -- 주문 연결 (해당 시)
    material_code TEXT NOT NULL,       -- box_small, aircap, ice_pack 등
    material_name TEXT,
    quantity INT NOT NULL,
    unit_cost NUMERIC NOT NULL,        -- 개당 원가
    total_cost NUMERIC NOT NULL,
    used_by UUID,                      -- 사용 작업자
    used_at TIMESTAMPTZ DEFAULT NOW(),
    note TEXT
);

-- ============================================
-- 보관료 일일 스냅샷 (정확한 일할 계산용)
-- ============================================
CREATE TABLE storage_daily_snapshot (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id UUID REFERENCES operators(id),
    client_id UUID REFERENCES clients(id),
    warehouse_id UUID REFERENCES warehouses(id),
    zone_id UUID,
    snapshot_date DATE NOT NULL,
    -- 수량 스냅샷
    total_sku_count INT DEFAULT 0,
    total_unit_count INT DEFAULT 0,
    total_cbm NUMERIC DEFAULT 0,       -- 총 부피 (CBM)
    total_pallets NUMERIC DEFAULT 0,   -- 총 팔레트 수
    -- 비용 계산
    storage_type TEXT,                 -- ambient/cold/frozen
    daily_rate NUMERIC,                -- 적용 일단가
    daily_cost NUMERIC,                -- 당일 보관비
    -- 장기보관
    over_60_days_cbm NUMERIC DEFAULT 0,
    over_90_days_cbm NUMERIC DEFAULT 0,
    surcharge_amount NUMERIC DEFAULT 0,
    UNIQUE(operator_id, client_id, warehouse_id, snapshot_date)
);

-- ============================================
-- 이의제기/조정 요청
-- ============================================
CREATE TABLE billing_disputes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID REFERENCES billing_invoices(id),
    client_id UUID REFERENCES clients(id),
    dispute_type TEXT,                 -- overcharge / missing_item / wrong_qty / other
    description TEXT NOT NULL,
    disputed_amount NUMERIC,
    status TEXT DEFAULT 'submitted',   -- submitted → reviewing → resolved → rejected
    resolution_note TEXT,
    resolved_amount NUMERIC,           -- 실제 조정된 금액
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by UUID
);
```

### 6.5 영상 관리 (기존 packing_jobs 테이블 확장)

```sql
-- 기존 packing_jobs에 operator_id, client_id 컬럼 추가로 대응
-- 별도 packing_videos 테이블은 불필요 (packing_jobs가 이미 video_path, video_size 보유)
-- 고객사 포털 조회용 뷰만 추가

CREATE VIEW client_packing_videos AS
SELECT
    pj.id, pj.scanned_barcode, pj.order_no, pj.channel,
    pj.product_name, pj.video_path, pj.video_size_bytes,
    pj.video_duration_ms, pj.started_at, pj.completed_at,
    pj.operator_id, pj.client_id
FROM packing_jobs pj
WHERE pj.status = 'completed'
  AND pj.video_path IS NOT NULL;
-- RLS 정책으로 client_id 필터 적용
```

---

## 7. 다중 3PL 운영사 관리 (Multi-Operator)

### 7.1 SaaS 플랫폼 계층 구조

```
┌─────────────────────────────────────────────────────┐
│              SaaS Platform (우리 = 플랫폼 운영)       │
│                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ 1번 3PL 운영사│  │ 2번 3PL 운영사│  │ 3번 3PL    │ │
│  │ (A 풀필먼트)  │  │ (B 물류)     │  │ (C 로지)   │ │
│  ├──────────────┤  ├──────────────┤  ├────────────┤ │
│  │ 고객사 A-1   │  │ 고객사 B-1   │  │ 고객사 C-1 │ │
│  │ 고객사 A-2   │  │ 고객사 B-2   │  │ 고객사 C-2 │ │
│  │ 고객사 A-3   │  │ 고객사 B-3   │  │ ...        │ │
│  │ ...          │  │ ...          │  │            │ │
│  ├──────────────┤  ├──────────────┤  ├────────────┤ │
│  │ 직원 10명    │  │ 직원 5명     │  │ 직원 3명   │ │
│  │ 패킹 작업자 8│  │ 패킹 작업자 4│  │ 패킹 2명   │ │
│  │ 창고 2개     │  │ 창고 1개     │  │ 창고 1개   │ │
│  └──────────────┘  └──────────────┘  └────────────┘ │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │ 플랫폼 슈퍼 관리자 (우리)                         │ │
│  │ - 전체 운영사 관리, 요금제 관리, 시스템 모니터링  │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 7.2 페이지 분리 전략: 서브도메인 방식 (권장)

```
3PL 운영사별 접속 분리:

방안 A: 서브도메인 (권장)
├── a-fulfillment.3plsaas.com  → 1번 3PL (A 풀필먼트)
├── b-logistics.3plsaas.com    → 2번 3PL (B 물류)
├── c-logi.3plsaas.com         → 3번 3PL (C 로지)
└── admin.3plsaas.com          → 플랫폼 관리자

장점: 완전히 분리된 느낌, 각 3PL 고유 브랜딩 가능
구현: Flask의 subdomain 매칭 또는 미들웨어에서 호스트명 → operator_id 매핑

방안 B: URL prefix
├── 3plsaas.com/op/a-fulfillment/...
├── 3plsaas.com/op/b-logistics/...
└── 3plsaas.com/admin/...

장점: 인프라 단순, SSL 인증서 1개
단점: 브랜딩 어려움, URL 길어짐

방안 C: 커스텀 도메인 (프리미엄)
├── wms.a-fulfillment.co.kr    → 1번 3PL 자체 도메인
└── 3plsaas.com/op/b-logistics → 2번 3PL 기본 도메인

→ Phase 1은 B안(URL prefix), Phase 2에서 A안(서브도메인) 지원 추천
```

### 7.3 고객사 직원 관리 구조

```
┌─────────────────────────────────────────────────────────┐
│                 사용자 계층 구조                          │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Platform Level (플랫폼 관리자 — 우리)                   │
│  └── super_admin: 전체 운영사/요금/시스템 관리            │
│                                                          │
│  Operator Level (3PL 운영사)                              │
│  ├── owner: 운영사 대표 (모든 권한 + 결제/계약)           │
│  ├── admin: 시스템 관리 (직원/고객사 관리)                │
│  ├── manager: 운영 책임 (주문/재고/정산 관리)             │
│  ├── warehouse_mgr: 창고 관리 (입출고/재고)               │
│  ├── cs: 고객 응대 (주문 조회/수정, 반품 처리)            │
│  ├── packing_lead: 패킹 리더 (작업 배정/관리)             │
│  ├── packing_worker: 패킹 작업자 (피킹/패킹/출고)        │
│  └── viewer: 조회 전용                                   │
│                                                          │
│  Client Level (고객사 = 위탁사)                           │
│  ├── client_owner: 고객사 대표 (모든 고객사 기능)         │
│  ├── client_admin: 고객사 관리자 (직원 관리 + 설정)       │
│  ├── client_staff: 고객사 직원 (주문/재고 조회, 입고요청) │
│  └── client_viewer: 조회 전용 (재고/주문 확인만)          │
│                                                          │
└─────────────────────────────────────────────────────────┘

핵심 규칙:
1. 3PL 운영사 직원은 자기 운영사의 모든 고객사 데이터 접근 가능 (역할에 따라)
2. 고객사 직원은 자기 고객사 데이터만 접근 가능 (절대 다른 고객사 불가)
3. 고객사 admin이 자기 회사 직원 추가/삭제/역할 변경 가능
4. 3PL 운영사 admin이 고객사 계정 생성/비활성화 가능
```

```sql
-- platform_users 테이블에 직원 관리 필드 추가
ALTER TABLE platform_users ADD COLUMN
    invited_by UUID,                    -- 초대한 사람 (감사 추적)
    invitation_status TEXT DEFAULT 'active',  -- invited → active → suspended
    department TEXT,                     -- 부서 (고객사 내부 구분)
    permissions JSONB DEFAULT '{}',     -- 세부 권한 커스텀
    -- permissions 예시:
    -- {"can_create_inbound": true, "can_view_billing": false,
    --  "can_download_videos": true, "max_export_rows": 1000}
    notification_settings JSONB DEFAULT '{}';
    -- {"email_on_order": true, "email_on_stock_alert": true,
    --  "kakao_on_shipping": false}
```

### 7.4 데이터 격리 매트릭스

```
누가 무엇을 볼 수 있는가:

                    │ 자사 데이터 │ 타 고객사 │ 타 운영사 │ 플랫폼 전체
────────────────────┼────────────┼──────────┼──────────┼───────────
플랫폼 super_admin  │     ✅     │    ✅    │    ✅    │    ✅
운영사 owner/admin  │     ✅     │    ✅*   │    ❌    │    ❌
운영사 manager      │     ✅     │    ✅*   │    ❌    │    ❌
운영사 packing      │    일부**  │   일부** │    ❌    │    ❌
고객사 owner/admin  │     ✅     │    ❌    │    ❌    │    ❌
고객사 staff        │    일부*** │    ❌    │    ❌    │    ❌
고객사 viewer       │   조회만   │    ❌    │    ❌    │    ❌

*  자기 운영사 소속 고객사들만
** 작업 배정된 건만
*** 권한 설정에 따라 (billing 제외 등)
```

---

## 8. 서버 안정성 및 장애 대응

### 8.1 SaaS 안정성 요구사항

```
가용성 목표:
├── Phase 1: 99.5% (월 약 3.6시간 다운타임 허용)
├── Phase 2: 99.9% (월 약 43분)
└── Phase 3: 99.95% (월 약 22분)

현재 인프라 (autotool):
├── Render (단일 인스턴스) → 단일 장애점 (SPOF)
├── Supabase (관리형) → 자체 HA 보유
└── 모니터링: 없음
```

### 8.2 장애 유형별 대응

```
┌─────────────────────────────────────────────────────────┐
│ 장애 유형          │ 영향              │ 대응 전략        │
├────────────────────┼───────────────────┼─────────────────┤
│ 앱 서버 다운       │ 전체 서비스 중단   │ 다중 인스턴스    │
│ (Render 장애)      │                   │ + 로드밸런서     │
│                    │                   │ + 헬스체크       │
├────────────────────┼───────────────────┼─────────────────┤
│ DB 연결 끊김       │ 전체 서비스 중단   │ Connection Pool  │
│ (Supabase 장애)    │                   │ + Retry 로직     │
│                    │                   │ + 읽기 캐시      │
├────────────────────┼───────────────────┼─────────────────┤
│ 마켓플레이스 API   │ 주문 수집 지연     │ 큐 기반 재시도   │
│ 장애               │                   │ + 수동 엑셀 대체 │
├────────────────────┼───────────────────┼─────────────────┤
│ 택배사 API 장애    │ 송장 발행 불가     │ 대체 택배사 전환 │
│                    │                   │ + 수동 발행 모드 │
├────────────────────┼───────────────────┼─────────────────┤
│ 스토리지 장애      │ 영상 저장 불가     │ 로컬 임시저장    │
│ (Supabase Storage) │                   │ + 재업로드 큐    │
├────────────────────┼───────────────────┼─────────────────┤
│ 트래픽 급증        │ 응답 지연/타임아웃 │ 오토스케일링     │
│ (블프, 이벤트)     │                   │ + Rate Limiting  │
└────────────────────┴───────────────────┴─────────────────┘
```

### 8.3 인프라 발전 로드맵

```
Phase 1 (MVP) — 최소 비용, 기본 안정성
┌──────────────────────────┐
│ Render                   │
│ ├── Web Service (1대)    │
│ ├── Background Worker    │
│ │   (주문수집, 정산 배치)│
│ └── Health Check 설정    │
├──────────────────────────┤
│ Supabase (관리형)        │
│ ├── DB + RLS             │
│ ├── Storage (영상)       │
│ └── Auth                 │
├──────────────────────────┤
│ 모니터링                 │
│ ├── UptimeRobot (무료)   │
│ ├── Sentry (에러 추적)   │
│ └── 슬랙 알림            │
└──────────────────────────┘

Phase 2 (성장) — 다중화 + 캐싱
┌──────────────────────────┐
│ Render / Railway / Fly.io│
│ ├── Web (2+ 인스턴스)    │
│ ├── Worker (1+ 인스턴스) │
│ └── 로드밸런서           │
├──────────────────────────┤
│ Redis (Upstash 등)       │
│ ├── 세션 공유            │
│ ├── 재고 캐시            │
│ └── 작업 큐              │
├──────────────────────────┤
│ Supabase                 │
│ ├── Connection Pooling   │
│ ├── Read Replica (옵션)  │
│ └── 대형 고객 별도 DB    │
├──────────────────────────┤
│ 모니터링 강화            │
│ ├── Grafana 대시보드     │
│ ├── DB 성능 모니터       │
│ └── 응답시간 알림        │
└──────────────────────────┘

Phase 3 (상용) — 엔터프라이즈급
┌──────────────────────────┐
│ AWS / GCP                │
│ ├── ECS/Cloud Run 오토스케일│
│ ├── CloudFront CDN       │
│ ├── WAF (웹방화벽)       │
│ └── 멀티 리전 (옵션)     │
├──────────────────────────┤
│ DB                       │
│ ├── RDS/Cloud SQL        │
│ │   (Supabase 이탈 시)   │
│ ├── 자동 백업 (매일)     │
│ └── Point-in-time 복구   │
└──────────────────────────┘
```

### 8.4 데이터 보호

```
백업 전략:
├── DB: Supabase 자동 백업 (7일) + 수동 주간 백업
├── 영상: 보관기간 정책 (기본 30일, 고객사별 설정)
├── 설정/코드: Git + CI/CD
└── 중요 데이터: 재고 스냅샷 일일 백업

복구 절차:
├── RTO (복구 시간 목표): Phase 1 = 4시간, Phase 2 = 1시간
├── RPO (복구 시점 목표): Phase 1 = 24시간, Phase 2 = 1시간
└── 복구 매뉴얼 + 정기 복구 테스트

운영사별 데이터 분리 보장:
├── RLS 정책으로 쿼리 수준 격리
├── API 레벨에서 operator_id 검증
├── 관리자 도구에서도 교차 접근 불가
└── 데이터 삭제 시 운영사별 완전 분리 삭제
```

---

## 9. 실시간 처리 설계

### 7.1 실시간 재고 업데이트

```
필요 시나리오:
1. 패킹센터에서 출고 처리 → 고객사 포털에 즉시 반영
2. 여러 작업자가 동시에 같은 재고 접근 → 동시성 제어
3. 재고 부족 알림 → 관리자/고객사에 실시간 알림

구현 방안:
├── Phase 1: Polling (5초 간격 AJAX) — 가장 단순
├── Phase 2: Supabase Realtime (DB 변경 구독)
└── Phase 3: WebSocket + Redis Pub/Sub — 최고 성능
```

### 7.2 동시성 제어

```
문제: 2명이 동시에 같은 상품 피킹 → 재고 마이너스 가능

해결:
1. DB 수준: SELECT FOR UPDATE (행 잠금)
2. 애플리케이션: 피킹지시 배정 시 재고 예약 (reserved_qty)
3. 작업 완료 시: reserved → 실제 차감
4. 타임아웃: 30분 미처리 피킹지시 → 예약 해제
```

---

## 8. 개발 로드맵

### Phase 1 — MVP (4-6주)

```
Week 1-2: 기반 구축
├── 멀티테넌트 기반 (operator/client 구조)
├── 인증/인가 (3개 포털 분리)
├── 창고/구역 관리 기본
└── 고객사 관리 기본

Week 3-4: 핵심 기능
├── 고객사별 재고 관리 (입고/출고/조회)
├── 주문 수집 (기존 마켓플레이스 연동 재사용)
├── 피킹/패킹 워크플로우
└── 송장 출력/전송 (기존 택배사 API 재사용)

Week 5-6: 정산 + 포털
├── 고객사 포털 (재고/주문 조회)
├── 패킹센터 포털 (작업 화면)
├── 기본 정산 기능
└── 테스트 + 안정화
```

### Phase 2 — 고도화 (4-6주)

```
├── 발주 추천 시스템
├── 영상 녹화/관리
├── 다중 채널 확장 (11번가, G마켓 등)
├── 실시간 재고 (WebSocket/Realtime)
├── 리포트/대시보드 고도화
└── 엑셀 일괄 주문 처리
```

### Phase 3 — 상용화 (4-6주)

```
├── 요금제/결제 시스템
├── 온보딩 플로우
├── 홈페이지/랜딩 페이지
├── 사용자 가이드/헬프센터
├── 성능 최적화
└── 보안 감사 + 장애 대비
```

---

## 9. 기존 autotool 코드 재사용 분석

### 재사용 가능 (높음)

| 모듈 | 위치 | 재사용 방법 |
|------|------|-------------|
| 마켓플레이스 API 클라이언트 | `services/marketplace/` | 거의 그대로 사용, tenant 필터 추가 |
| 택배사 API (송장) | `services/courier/` | 그대로 사용 |
| 엑셀 I/O | `services/excel_io.py` | 그대로 사용 |
| 주문 처리 엔진 | `services/order_processor.py` | 고객사 분리 로직 추가 |
| 재고 서비스 | `services/stock_service.py` | 대폭 확장 (위치/LOT 추가) |
| RBAC 패턴 | `auth.py` | 확장 (portal + tenant 추가) |
| DB 패턴 | `db_supabase.py` | 기반 유지, RLS 추가 |

### 재사용 가능 (중간 — 수정 필요)

| 모듈 | 변경 사항 |
|------|-----------|
| 입고 관리 | 고객사 입고요청 플로우 추가 |
| 출고 관리 | 피킹→패킹→출고 워크플로우 세분화 |
| 재고 조정 | 고객사별 조정 + 승인 플로우 |
| 대시보드 | 포털별 3종 대시보드 |

### 새로 개발 필요

| 모듈 | 설명 |
|------|------|
| 창고/구역/위치 관리 | 현재 없음 |
| 고객사 포털 | 완전 신규 |
| 패킹센터 포털 | 현재 packing.py 대폭 확장 |
| 발주 추천 | planning.py 참고하되 신규 |
| 영상 관리 | 기존 packing.py 보강 (operator/client 분리 추가) |
| 비용 청구/빌링 | 완전 신규 (포장비/합포장비/부자재비/창고비/정산) |
| 멀티테넌트 인프라 | 현재 패턴 확장 |

---

## 10. 리스크 및 검토 필요 사항

### 기술적 리스크

| 항목 | 리스크 | 대응 방안 |
|------|--------|-----------|
| 동시성 | 다수 작업자 동시 재고 접근 | DB 행 잠금 + 예약 수량 패턴 |
| 실시간성 | Polling 한계, WebSocket 복잡 | Phase 1은 Polling, Phase 2에서 전환 |
| 영상 저장 | 스토리지 비용 증가 | 보관기간 정책 + 자동삭제 |
| 채널 확장 | 채널마다 API 스펙 다름 | 어댑터 패턴 + 채널별 매핑 테이블 |
| DB 규모 | 주문/재고 데이터 급증 | 파티셔닝 + 아카이빙 정책 |

### 사업적 검토 필요

| 항목 | 질문 |
|------|------|
| 요금제 | 건당? 월정액? 혼합? 프리티어? |
| 타겟 규모 | 소형(일 100건)? 중형(일 1000건)? 대형(일 10000건)? |
| 온보딩 | 셀프서비스? 컨설팅 동반? |
| 경쟁사 | 파스토, 두손컴퍼니, 품고 등 대비 차별점? |
| 규제 | 물류 관련 법규, 개인정보보호 |

---

## 11. GPT/Gemini 검토 요청 포인트

이 문서를 GPT/Gemini에 전달 시 아래 질문들에 대한 의견을 요청:

1. **멀티테넌시 전략**: RLS vs DB-per-Tenant, Phase별 전환 전략이 적절한가?
2. **3개 포털 분리**: 물리적(별도 앱) vs 논리적(URL prefix) vs 서브도메인 — 어느 쪽이 유리한가?
3. **다중 3PL 운영사 관리**: 운영사별 완전 격리 방법, 운영사 간 데이터 유출 방지 전략?
4. **고객사 직원 관리**: 고객사가 자체 직원 관리할 때 권한 체계 설계 적절한가?
5. **비용 청구 시스템**: 포장비/합포장비/부자재비/창고비 계산 로직, 업계 표준 요금 체계?
6. **보관료 계산**: CBM 기준 vs 팔레트 기준 vs SKU당, 일할계산 방법 최적화?
7. **실시간 재고**: Supabase Realtime 활용 가능성 vs WebSocket 직접 구현?
8. **채널 확장 전략**: 어댑터 패턴 외에 더 나은 패턴이 있는가?
9. **발주 추천 알고리즘**: 단순 소진율 외에 계절성, 프로모션 등 고려 방법?
10. **서버 안정성**: SaaS 운영 시 서버 다운 대비, Render 단일 인스턴스 한계와 전환 시점?
11. **기존 Flask 유지 vs FastAPI 전환**: SaaS 규모에서의 판단?
12. **프론트엔드**: Jinja2 유지 vs Vue/React SPA 전환 시점?
13. **추가 기능 제안**: 3PL 업계에서 빠진 필수 기능이 있는가?
14. **홈페이지 구조**: SaaS 랜딩페이지 필수 구성요소?

---

## 부록: 용어 정리

| 용어 | 설명 |
|------|------|
| 3PL | Third-Party Logistics, 물류 대행 (풀필먼트) |
| Operator | 3PL 운영사 (우리의 고객사 = SaaS 가입자) |
| Client | 3PL 운영사의 고객 (물류를 위탁하는 셀러/제조사) |
| Tenant | 데이터 격리 단위 (= Operator) |
| SKU | Stock Keeping Unit, 재고관리 단위 |
| LOT | 제조 로트, 같은 배치로 생산된 제품 그룹 |
| FIFO | First In First Out, 선입선출 |
| WMS | Warehouse Management System, 창고관리 시스템 |
| RLS | Row-Level Security, 행 수준 보안 |
| Picking | 주문에 맞게 창고에서 상품을 꺼내는 작업 |
| Packing | 꺼낸 상품을 포장하는 작업 |
| Inbound | 입고 (외부 → 창고) |
| Outbound | 출고 (창고 → 외부) |
