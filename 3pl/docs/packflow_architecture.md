# PackFlow 통합 물류 시스템 — 아키텍처 구조서

> 작성일: 2026-03-16 | 버전: 1.0
> 런칭 목표: 2026년 5월 (3~4월 시뮬레이션 검증)

---

## 1. 시스템 개요

PackFlow는 **이유식 재료 주문처리 자동화(auto_tool)** + **3PL 물류 SaaS(PackFlow SaaS)** 두 축으로 구성된 통합 물류 시스템입니다.

```
┌─────────────────────────────────────────────────────────────┐
│                    PackFlow 통합 시스템                       │
├──────────────────────────┬──────────────────────────────────┤
│   auto_tool (포트 5000)   │   PackFlow SaaS (포트 5003)      │
│   자체 물류 운영 + 회계    │   3PL 멀티테넌트 SaaS            │
│   37 blueprints           │   4 blueprints (operator/       │
│   35+ services            │     client/packing/api)          │
│   8채널 주문수집           │   13 repositories               │
│   마켓플레이스 API 연동    │   8 services                    │
├──────────────────────────┴──────────────────────────────────┤
│                  공통 인프라: Supabase + Render               │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. auto_tool — 자체 물류 운영 시스템

### 2.1 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | Flask (Application Factory) |
| DB | Supabase (PostgreSQL) |
| Frontend | Bootstrap 5 + Jinja2 |
| 인증 | Flask-Login + 세션 기반 |
| 배포 | Render |
| 데이터 무결성 | core/ValidationEngine + IntegrityMonitor |

### 2.2 블루프린트 구조 (37개)

#### 주문/물류 (핵심)
| 블루프린트 | 기능 |
|-----------|------|
| `orders` | 주문 수집/관리 (8채널 통합) |
| `stock` | 재고 조회 |
| `inbound` | 입고 관리 |
| `outbound` | 출고 관리 |
| `production` | 생산 관리 |
| `transfer` | 창고 이동 |
| `adjustment` | 재고 조정 |
| `shipment` | 배송 관리 |
| `packing` | 패킹센터 |
| `repack` | 리패킹 |
| `set_assembly` | 세트 조립 |
| `etc_outbound` | 기타 출고 |

#### 분석/관리
| 블루프린트 | 기능 |
|-----------|------|
| `dashboard` | 대시보드 |
| `aggregation` | 집계 |
| `ledger` | 원장 |
| `history` | 이력 조회 |
| `revenue` | 매출 |
| `reconciliation` | 정산 대사 |
| `planning` | 생산 계획 |
| `yield_mgmt` | 수율 관리 |
| `closing` | 마감 |
| `integrity` | 무결성 모니터 |

#### 기초/마스터
| 블루프린트 | 기능 |
|-----------|------|
| `base_data` | 기초 데이터 |
| `master` | 마스터 관리 |
| `trade` | 거래처 |
| `bom_cost` | BOM 원가 |
| `price_mgmt` | 가격 관리 |
| `promotions` | 프로모션 |
| `mobile` | 모바일 |

#### 회계/재무
| 블루프린트 | 기능 |
|-----------|------|
| `finance` | 재무 |
| `accounting` | 회계 |
| `bank` | 은행 거래 (KB국민/부산/기업/우리) |
| `tax_invoice` | 세금계산서 |
| `journal` | 분개장 |
| `hr` | 인사/급여 (4대보험, 6단계 세율) |

#### 외부 연동
| 블루프린트 | 기능 |
|-----------|------|
| `marketplace` | 마켓플레이스 API (쿠팡/네이버/Cafe24) |

### 2.3 서비스 레이어 (35+)

```
services/
├── 주문/물류
│   ├── order_processor.py          # 주문 수집 파이프라인
│   ├── channel_config.py           # 8채널 설정
│   ├── outbound_service.py         # 출고
│   ├── inbound_service.py          # 입고
│   ├── stock_service.py            # 재고
│   ├── transfer_service.py         # 이동
│   ├── repack_service.py           # 리패킹
│   ├── set_assembly_service.py     # 세트 조립
│   ├── production_service.py       # 생산
│   └── etc_outbound_service.py     # 기타 출고
│
├── 회계/재무
│   ├── bank_service.py             # 은행 거래
│   ├── bank_excel_service.py       # 은행 엑셀 업로드
│   ├── card_service.py             # 카드
│   ├── journal_service.py          # 분개
│   ├── matching_service.py         # 매칭
│   ├── settlement_service.py       # 정산
│   ├── tax_invoice_service.py      # 세금계산서
│   ├── pnl_service.py              # 손익표
│   ├── hr_service.py               # 급여 (일할계산)
│   ├── financial_report_service.py # 재무보고
│   ├── revenue_service.py          # 매출
│   ├── ledger_service.py           # 원장
│   ├── actual_cost_service.py      # 실제 원가
│   └── bom_cost_service.py         # BOM 원가
│
├── 분석/리포트
│   ├── dashboard_service.py        # 대시보드
│   ├── report_service.py           # 리포트
│   ├── sales_analysis_service.py   # 매출 분석
│   ├── shipment_stats_service.py   # 배송 통계
│   ├── aggregator.py               # 집계
│   ├── planning_service.py         # 계획
│   ├── reconciliation_service.py   # 대사
│   └── yield_service.py            # 수율
│
├── marketplace/                    # 마켓플레이스 API 클라이언트
│   ├── base_client.py
│   ├── coupang_client.py           # 쿠팡 (HMAC-SHA256)
│   ├── naver_client.py             # 네이버 (OAuth2)
│   ├── cafe24_client.py            # Cafe24 (OAuth2 refresh)
│   ├── naver_ad_client.py          # 네이버 광고
│   ├── marketplace_sync_service.py
│   └── marketplace_validation_service.py
│
├── courier/
│   └── cj_client.py                # CJ대한통운
│
└── 유틸
    ├── excel_io.py
    ├── storage_helper.py
    ├── tz_utils.py
    └── validation.py
```

### 2.4 주문 수집 채널 (8개)

| 채널 | 연동 방식 |
|------|----------|
| 스마트스토어 | API (OAuth2) |
| 쿠팡 | API (HMAC-SHA256) |
| 옥션/G마켓 | 엑셀 업로드 |
| 자사몰 (Cafe24) | API (OAuth2) |
| 오아시스 | 엑셀 업로드 |
| 11번가 | 엑셀 업로드 |
| 카카오 | 엑셀 업로드 |
| 해미애찬 | 엑셀 업로드 |

### 2.5 데이터 무결성 (core/)

```
core/
├── validation_engine.py   # 입력 검증, 비즈니스 룰 체크
└── integrity_monitor.py   # 재고/원장 정합성 모니터링
```

---

## 3. PackFlow SaaS — 3PL 멀티테넌트 플랫폼

### 3.1 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | Flask (Application Factory) |
| DB | Supabase (PostgreSQL) |
| Frontend | Bootstrap 5 + Jinja2 |
| 인증 | Flask-Login + CSRF (Flask-WTF) |
| 멀티테넌트 | operator_id 기반 Row-Level 격리 |
| 배포 | Render (Docker) |

### 3.2 멀티테넌트 아키텍처

```
┌──────────────────────────────────────────┐
│              Supabase DB                  │
│  ┌─────────────────────────────────────┐ │
│  │  모든 테이블에 operator_id 컬럼      │ │
│  │  BaseRepository.set_tenant()        │ │
│  │  → before_request 훅에서 자동 주입   │ │
│  └─────────────────────────────────────┘ │
└──────────────────────────────────────────┘
         ▲
         │ operator_id 필터링
    ┌────┴────┐
    │ 운영사A  │  운영사B  │  운영사C  │
    │ (고객5)  │  (고객3)  │  (고객8)  │
    └─────────┘
```

### 3.3 3포털 구조

```
┌─────────────────────────────────────────────────────────┐
│                  PackFlow SaaS                           │
├───────────────┬──────────────────┬──────────────────────┤
│  운영사 포털   │   고객사 포털     │   패킹센터 포털      │
│  /operator/*  │   /client/*      │   /packing/*         │
│               │                  │                      │
│  - 대시보드    │  - 대시보드       │  - 대시보드          │
│  - 주문관리    │  - 주문조회       │  - 피킹 대기열       │
│  - 출고관리    │  - 재고조회       │  - 바코드 스캔       │
│  - 재고현황    │  - 과금내역       │  - 검수/촬영         │
│  - 수불부      │  - 엑셀 내보내기  │  - 피킹 상세         │
│  - 상품마스터  │                  │  - 실적 통계         │
│  - 입고관리    │                  │                      │
│  - 재고조정    │                  │                      │
│  - 고객사관리  │                  │                      │
│  - 창고/로케   │                  │                      │
│  - 과금관리    │                  │                      │
│  - 사용자관리  │                  │                      │
│  - 엑셀 내보  │                  │                      │
├───────────────┴──────────────────┴──────────────────────┤
│  API 블루프린트 (/api/*) — CSRF 면제, REST JSON          │
└─────────────────────────────────────────────────────────┘
```

### 3.4 레포지토리 패턴 (13개)

모든 레포지토리는 `BaseRepository`를 상속하며, `operator_id` 기반 테넌트 격리가 자동 적용됩니다.

```
repositories/
├── base.py                    # BaseRepository (set_tenant, CRUD 공통)
├── warehouse_repo.py          # 창고/로케이션
├── inventory_repo.py          # 재고/SKU/수불 (low_stock, expiry 알림)
├── order_repo.py              # 주문
├── packing_repo.py            # 패킹 세션
├── picking_repo.py            # 피킹 리스트
├── billing_repo.py            # 운영사 SaaS 과금
├── client_billing_repo.py     # 고객사 물류비 과금
├── client_repo.py             # 고객사 마스터
├── client_rate_repo.py        # 고객사별 단가표
├── client_marketplace_repo.py # 고객사 마켓플레이스 연동
└── user_repo.py               # 사용자
```

### 3.5 서비스 레이어 (8개)

```
services/
├── warehouse_service.py         # 입고 처리 (process_inbound)
├── inventory_service.py         # 재고 변동 (log_movement, adjust_stock)
├── picking_service.py           # FIFO 피킹 + 유통기한 만료 차단
├── billing_service.py           # 운영사 SaaS 과금
├── client_billing_service.py    # 고객사 과금 (7카테고리, DLQ 패턴)
├── scan_validator.py            # 바코드 스캔 검증
├── shipment_guard.py            # 출고 유형별 가드 (일반/반품/이동)
└── tz_utils.py                  # 타임존 유틸
```

### 3.6 과금 시스템

#### 7개 카테고리 × 21개 프리셋

| 카테고리 | 프리셋 예시 | 설명 |
|---------|-----------|------|
| `inbound` | 입고검수, 입고적재 | 입고 시 자동 과금 |
| `outbound` | 피킹, 패킹, 출고검수 | 출고 시 자동 과금 |
| `storage` | 일반보관, 냉장보관, 냉동보관 | 온도구간별 보관비 |
| `courier` | 택배비, 착불택배 | 택배 연동 |
| `supply` | 박스, 테이프, 에어캡 | 부자재 |
| `return` | 반품검수, 재입고 | 반품 처리 |
| `vas` | 라벨링, 번들링, 키팅 | 부가서비스 |

#### DLQ(Dead Letter Queue) 패턴
```
과금 기록 시도 → 실패 시 failed_billing_events 테이블에 저장
                → 재처리 배치로 복구
                → 물류 처리는 과금 실패와 무관하게 정상 진행
```

#### 보관비 고도화 (v2)
- SKU별 `storage_temp` (ambient/cold/frozen) → 단가표 fee_name 키워드 매칭
- `daily_inventory_snapshot` 테이블로 일별 정확 계산
- `storage_unit`: per_item / per_pallet / per_cbm / per_location

### 3.7 출고 유형

| shipment_type | 설명 | 재고 변동 |
|--------------|------|----------|
| `normal` | 일반 출고 | 차감 |
| `return` | 반품 출고 | 복원 (adjust_stock + log_movement) |
| `transfer` | 창고 이동 | 차감 → 입고 |

### 3.8 마이그레이션 이력

| # | 파일 | 내용 |
|---|------|------|
| 001 | `initial_schema.sql` | 기본 스키마 (users, clients, skus, orders 등) |
| 002 | `test_data.sql` | 테스트/시드 데이터 |
| 003 | `client_rates.sql` | 고객사 단가 테이블 |
| 004 | `wms_core.sql` | WMS 핵심 (warehouse, location, stock) |
| 005 | `client_marketplace.sql` | 고객사 마켓플레이스 연동 |
| 006 | `outbound_enhanced.sql` | 출고 고도화 (shipment_type) |
| 007 | `billing_enhanced.sql` | 7카테고리 과금, 21 프리셋 |
| 008 | `security_and_schema_fixes.sql` | FK 제약, DLQ 테이블, 보안 |
| 009 | `operational_enhancements.sql` | min/max 재고, 보관비 단위, 일별 스냅샷 |

---

## 4. 보안 체계

### 4.1 인증/인가
- Flask-Login 세션 기반 인증
- 역할 기반 접근 제어: `operator` / `client_admin` / `client_staff` / `packer`
- `@_require_operator`, `@_require_client` 데코레이터

### 4.2 CSRF 보호
- Flask-WTF CSRFProtect 전역 적용
- `<meta name="csrf-token">` + JS 자동 주입 (33개 폼)
- API 블루프린트는 CSRF 면제

### 4.3 입력 검증
- 파일 업로드 MIME 타입 검증 (엑셀, 동영상)
- 바코드 스캔 검증 (scan_validator)
- 테넌트 격리 검증 (API 요청 시 client_id 소속 확인)

---

## 5. 배포 구성

```
┌─────────────────┐     ┌─────────────────┐
│   Render Web     │     │   Render Web     │
│   auto_tool      │     │   PackFlow SaaS  │
│   :5000          │     │   :5003          │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────┬───────────────┘
                 ▼
        ┌────────────────┐
        │   Supabase DB   │
        │   PostgreSQL    │
        └────────────────┘
```

### Render 설정
- `render.yaml` + `Dockerfile` (3PL)
- `wsgi.py` 엔트리포인트
- 환경변수: `SUPABASE_URL`, `SUPABASE_KEY`, `SECRET_KEY`, `PORT`

---

## 6. 로드맵 및 검증 계획

### Phase 1: 시뮬레이션 검증 (2026년 3~4월)
- [ ] Migration 008, 009 Supabase 실행
- [ ] 고객사 테스트 데이터 투입
- [ ] 입고 → 보관 → 출고 풀사이클 테스트
- [ ] 과금 자동계산 정합성 검증
- [ ] DLQ 복구 시나리오 테스트
- [ ] 온도구간별 보관비 계산 검증
- [ ] 유통기한 만료 피킹 차단 테스트
- [ ] 반품 출고 재고 복원 검증
- [ ] 엑셀 내보내기 전 엔드포인트 테스트
- [ ] 멀티테넌트 격리 보안 테스트

### Phase 2: 런칭 준비 (2026년 4월)
- [ ] 실 고객사 온보딩 프로세스 정립
- [ ] 단가표 프리셋 커스터마이징
- [ ] 정산서 발행/발송 워크플로우
- [ ] 모니터링/알림 체계 구축

### Phase 3: 런칭 (2026년 5월~)
- [ ] 첫 고객사 라이브 운영 시작
- [ ] 피드백 기반 기능 개선
- [ ] 추가 마켓플레이스 API 연동 확대
