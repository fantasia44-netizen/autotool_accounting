# PackFlow 3PL SaaS — 구조 설계 완성도 검토 요청서

> **작성일**: 2026-03-15
> **목적**: PackFlow의 현재 아키텍처를 글로벌/국내 주요 3PL SaaS 플랫폼과 비교하여 **부족한 기능, 설계 보완점, 우선순위**를 도출
> **검토 대상**: GPT / Gemini (외부 AI 리뷰어)

---

## Part 1. PackFlow 현재 구현 상태

### 1.1 기술 스택
| 항목 | 스택 |
|------|------|
| Backend | Flask (Python 3.14) + Supabase (PostgreSQL) |
| Frontend | Jinja2 SSR + Bootstrap 5.3 |
| ORM | 없음 (Supabase REST API + Repository 패턴) |
| Multi-tenant | operator_id 기반 데이터 격리 |
| 인증 | Flask-Login + Role-based (@role_required) |
| 배포 | Render (Docker) |

### 1.2 포털 구조 (3개 분리)
| 포털 | URL Prefix | 대상 | 역할 |
|------|-----------|------|------|
| Operator | `/operator` | 3PL 운영사 | owner, admin, manager, warehouse, cs, viewer |
| Client | `/client` | 고객사(화주) | client_admin, client_staff, client_viewer |
| Packing | `/packing` | 패킹 작업자 | packing_lead, packing_worker |
| API | `/api/v1` | 외부 시스템 | (토큰 인증 예정) |

### 1.3 역할 계층 (13개)
```
플랫폼:  super_admin (0)
3PL:     owner (1) → admin (2) → manager (3) → warehouse (4) → cs (5) → viewer (6)
고객사:  client_admin (10) → client_staff (11) → client_viewer (12)
패킹:    packing_lead (20) → packing_worker (21)
```

---

## Part 2. 기능 모듈 상세

### 2.1 운영사 포탈 (Operator Portal)

#### A. 대시보드
- KPI 카드: 주문 수, SKU 수, 고객사 수, 출고 수
- 최근 주문 목록

#### B. 주문관리 (OMS)
| 기능 | 상태 |
|------|------|
| 주문 목록/상세 | O (상태/채널/고객사 필터) |
| 주문 상태 변경 | O (pending → confirmed → picking → packing → shipped → delivered) |
| 주문 보류/해제 | O (hold_flag, hold_reason, 감사로그) |
| 상태 변경 로그 | O (order_status_logs 테이블) |
| 외부 주문 수신 API | X (TODO — POST /api/v1/orders 스텁만) |
| 주문 자동 라우팅 | X |
| 주문 분할/병합 | X |
| 주문 수정/취소 | 상태변경만 (항목 수정 불가) |

#### C. 출고관리
| 기능 | 상태 |
|------|------|
| 일반출고 (송장 기반) | O |
| 반품출고 | O (shipment_type='return', 사유 기록) |
| 창고이동 | O (shipment_type='transfer', from/to warehouse, 재고 이동 기록) |
| 반품 재입고 처리 | △ (이력만 기록, 실재고 adjust_stock 최근 수정) |
| 출고 차단 검증 | O (shipment_guard.py — 취소/보류/중복 검증) |

#### D. 재고관리 (WMS Core)
| 기능 | 상태 |
|------|------|
| SKU 마스터 (CRUD) | O (바코드 필수) |
| SKU 엑셀 일괄 업로드 | O (openpyxl, 샘플 다운로드) |
| 로케이션별 재고 추적 | O (warehouse → zone → location) |
| Lot/유통기한 추적 | O (lot_number, expiry_date) |
| 2-Phase 재고: 예약 → 커밋 | O (reserve_stock → commit_stock) |
| 입고 처리 | O (+ 과금 훅) |
| 재고 조정 | O (adjustment 페이지) |
| 수불장 (이력) | O (inventory_movements) |
| 유통기한 임박 알림 | O (get_expiring_soon) |
| 안전재고 알림 | O (get_low_stock_items) |
| 사이클 카운트 | X |
| FIFO 출고 | O (유통기한 기준 예약) |
| 바코드/RFID | 바코드만 O |

#### E. 피킹
| 기능 | 상태 |
|------|------|
| 피킹리스트 자동 생성 | O (주문별/상품별/로케이션별) |
| 피킹 항목별 수량 갱신 | O (picked_qty) |
| 피킹 완료 처리 | O (complete_picking_list) |
| 웨이브 피킹 | X |
| AI 경로 최적화 | X |
| 배치 피킹 | X |

#### F. 패킹 (별도 포탈)
| 기능 | 상태 |
|------|------|
| 패킹 작업큐 | O |
| 바코드 스캔 검증 | O (scan_validator.py — 오출고 차단) |
| 영상 촬영/업로드 | O (Supabase Storage) |
| 작업자별 실적 통계 | O |
| Pack-to-Light | X |
| 부자재 입력/과금 연동 | X (record_packing_fee 준비만) |

#### G. 창고관리
| 기능 | 상태 |
|------|------|
| 창고 CRUD | O |
| 구역(Zone) 관리 | O (온도대별: 상온/냉장/냉동) |
| 로케이션 관리 | O |
| 멀티창고 | O (복수 창고 생성 가능) |
| 창고간 재고 통합 뷰 | X |
| 로케이션별 적재율 | X |

#### H. 고객사 관리
| 기능 | 상태 |
|------|------|
| 고객사 CRUD | O |
| 고객사별 SKU 관리 | O |
| 고객사별 요금표 | O (21개 프리셋, 8개 카테고리) |
| 마켓플레이스 API 인증 관리 | O (네이버/쿠팡/카페24) |
| SLA 설정 | X |
| 고객사 계약 관리 | X |

#### I. 과금/정산
| 기능 | 상태 |
|------|------|
| 과금 이벤트 자동 기록 | O (입고/출고/반품 훅) |
| 카테고리별 요금 | O (입고/출고/보관/택배/부자재/반품/부가서비스/기타) |
| 월별 정산서 | O (카테고리별 소계 + 상세) |
| 정산서 확정 | O (draft → confirmed) |
| 보관비 자동 계산 | △ (함수 존재, 트리거 없음) |
| 패킹 부자재 과금 | △ (함수 준재, UI 없음) |
| 정산서 PDF 다운로드 | X |
| 정산서 이메일 발송 | X |
| 과금 수동 등록/수정 | X |
| 회계 시스템 연동 | X |

#### J. 사용자 관리
| 기능 | 상태 |
|------|------|
| 사용자 목록 | O |
| 사용자 승인/비승인 | O |
| 역할 기반 메뉴 제어 | O (PAGE_REGISTRY) |
| 비밀번호 변경 | X |
| 초대 링크 | X |

### 2.2 고객사 포탈 (Client Portal)
| 기능 | 상태 |
|------|------|
| 대시보드 (최근 주문/재고/과금) | O |
| 재고 조회 | O |
| 주문 현황 (상태별 필터) | O |
| 출고 영상 조회 | O |
| 정산서 조회 | X |
| 주문 등록 | X |
| 입고 요청 | X |
| 반품 신청 | X |
| 리포트 다운로드 | X |

### 2.3 패킹센터 포탈 (Packing Portal)
| 기능 | 상태 |
|------|------|
| 작업 대시보드 | O |
| 작업큐 | O |
| 바코드 스캔 | O |
| 피킹 모드 | O |
| 실적 통계 | O |
| 영상 촬영 | O |

### 2.4 REST API
| 엔드포인트 | 상태 |
|-----------|------|
| GET /api/v1/health | O |
| POST /api/v1/orders | X (TODO) |
| GET /api/v1/inventory/<sku_code> | X (TODO) |
| 웹훅 (주문 상태 변경 알림) | X |
| OAuth2 / API Key 인증 | X |

---

## Part 3. DB 스키마 (22개 테이블)

| 테이블 | 용도 | 핵심 컬럼 |
|--------|------|---------|
| operators | 3PL 운영사 | id, name, business_no, plan |
| users | 사용자 | id, username, role, operator_id, client_id, is_approved |
| clients | 고객사(화주) | id, operator_id, name, business_no, contact_* |
| warehouses | 창고 | id, operator_id, name, address, storage_type |
| warehouse_zones | 구역 | id, warehouse_id, name, storage_temp |
| warehouse_locations | 로케이션 | id, zone_id, code |
| skus | 상품 | id, operator_id, client_id, sku_code, barcode, name |
| inventory_stock | 재고 | sku_id, location_id, quantity, reserved_qty, lot_number, expiry_date |
| inventory_movements | 수불장 | sku_id, movement_type, quantity, order_id |
| inventory_reservations | 예약 | order_id, sku_id, reserved_qty, status |
| orders | 주문 | id, operator_id, client_id, channel, order_no, status, hold_flag |
| order_items | 주문상세 | order_id, sku_id, quantity |
| order_status_logs | 상태로그 | order_id, old_status, new_status, changed_by |
| shipments | 출고 | order_id, invoice_no, shipment_type, client_id |
| picking_lists | 피킹리스트 | list_no, list_type, status, assigned_to |
| picking_list_items | 피킹항목 | picking_list_id, sku_id, expected_qty, picked_qty |
| packing_jobs | 패킹작업 | order_id, status, user_id, video_path |
| client_rates | 요금표 | client_id, fee_name, fee_type, amount, category |
| client_billing_logs | 과금로그 | client_id, year_month, fee_name, category, total_amount |
| client_invoices | 정산서 | client_id, year_month, total_amount, status |
| client_marketplace_credentials | 마켓플레이스 API | client_id, channel, api_client_id |
| billing_plans / billing_usage / billing_invoices | 플랫폼 과금 | operator_id, year_month |

---

## Part 4. 핵심 비즈니스 로직

### 4.1 주문 처리 Flow
```
외부 주문 수신 → orders (status=pending)
  → 주문 확정 (confirmed)
    → reserve_stock() — FIFO 유통기한순 재고 예약, 부족 시 전체 롤백
  → 피킹리스트 생성 (generate_picking_list)
    → picking_lists + items 자동 생성
  → 피킹 작업 (패킹포탈)
    → update_item_picked() — 수량 갱신, 상태 전이
  → 패킹 완료
    → commit_stock() — 실재고 차감
    → record_outbound_fee() — 출고비 자동 기록
  → 송장 등록
    → validate_order_for_shipping() — 출고 차단 검증
    → shipments (status=shipped)
```

### 4.2 재고 3-Phase
```
Phase 1 (예약): 주문 확정 시 → available = quantity - reserved_qty
Phase 2 (커밋): 패킹 완료 시 → reserved_qty, quantity 감소
Phase 3 (롤백): 주문 취소 시 → reserved_qty 복구
```

### 4.3 과금 Flow
```
이벤트 발생 → views.py 훅 → record_xxx_fee()
  → rate_repo.list_rates(client_id) — 카테고리별 요금표 조회
  → billing_repo.log_fee() — client_billing_logs 적재
  → 월별 정산 조회 → get_monthly_summary() — 카테고리별 집계
  → 정산서 확정 → client_invoices (draft → confirmed)
```

### 4.4 과금 카테고리 (8개, 21개 프리셋)
| 카테고리 | DB값 | 프리셋 항목 |
|---------|------|-----------|
| 입고비 | inbound | 입고검수비, 상차비, 하차비 |
| 출고비 | outbound | 출고작업비, 합포장추가비 |
| 보관비 | storage | 일반보관비, 냉장보관비, 냉동보관비 |
| 택배비 | courier | 기본택배비, 사이즈추가비, 중량추가비 |
| 부자재 | material | 박스, 아이스팩, 드라이아이스, 완충재, 테이프 |
| 반품 | return | 반품수수료, 반품검수비 |
| 부가서비스 | vas | 라벨부착, 키팅, 사진촬영 |
| 기타 | custom | 사용자 자유 입력 |

---

## Part 5. 글로벌/국내 주요 3PL SaaS 비교 자료

> 아래는 검토 시 비교 대상으로 참고할 주요 플랫폼 정보입니다.

### 5.1 글로벌 플랫폼

#### Extensiv (구 3PL Central) — 3PL 전문 WMS 업계 표준
- **핵심 모듈**: 3PL Warehouse Manager, Billing Manager, Integration Manager, Network Manager, SmartScan, Customer Portal
- **빌링**: 고객별 고유 빌링 계약, 모든 과금 이벤트 자동 추적, 실시간 과금 누적 → 자동 인보이싱, **QuickBooks 직접 연동**
- **SmartScan**: 웹 기반 모바일 스캐닝, 엔터프라이즈 하드웨어 + 스마트폰 모두 지원
- **연동**: 500개+ 플랫폼 (EDI + API)
- **멀티창고**: Network Manager로 4PL 운영 지원

#### ShipHero
- **AI 피킹 최적화**: 경로 최적화 + 스마트 배칭 → 이동거리 20~30% 감소
- **Pack-to-Light**: LED 가이드 패킹 → 처리량 450% 향상
- **노동력 관리**: 직원별 작업 할당, 유휴시간 최소화, 성과 추적
- **반품 관리**: 제품 유형/상태별 자동 재입고/폐기 규칙
- **과금**: $2,145/월 (3PL Plan), 무제한 고객 포털

#### ShipBob
- **AI 재고 분배**: 수요예측 기반 멀티 풀필먼트 센터 자동 재고 배분
- **실시간 동기화**: Shopify, Amazon, BigCommerce와 실시간 재고 싱크
- **과금 구조**: 보관료 + 피킹/패킹 + 배송비 + 부가서비스 (스케일 모델)

#### Logiwa IO
- **헤드리스 아키텍처**: 모든 UI에 대응하는 API 엔드포인트 (완전한 커스터마이징)
- **볼륨 기반 가격**: 사용자 수가 아닌 처리량 기준
- **웨이브 플래닝 + 자동 보충**

#### Deposco (Bright Suite)
- **Causal AI**: 수요/공급 변동의 근본 원인 식별
- **피킹 전략**: 웨이브/웨이브리스, 배치/벌크/케이스/팔레트
- **캐리어 레이트 쇼핑**: 주문별 최저 배송비 자동 탐색

### 5.2 국내 플랫폼

#### 사방넷 풀필먼트 — 국내 최대 규모
- **650개 쇼핑몰** 자동 주문 수집 (엑셀/수기 작업 불필요)
- **7,000+ 화주사** 사용 중
- 클라우드 웹 기반 WMS (HTML5, 모바일/태블릿 지원)
- 정부 지원: 중소기업 WMS 이용료 80% 할인

#### 셀러노트 '쉽다'
- 자체 WMS + 입고 전 전량 검수
- 네이버/쿠팡/11번가/카페24 API 자동 주문 수집 → 출고
- 수입 통관 데이터 기반 입고 시기 예측

#### 로지스팟 (LOGISPOT)
- 클라우드 네이티브 WMS
- RESTful Open API → ERP/WMS/OMS 연동
- 풀필먼트/3PL/포워딩/식품/제조/유통 지원

---

## Part 6. 검토 요청 사항

### 6.1 MUST-HAVE 기능 Gap 분석

아래 기능들은 글로벌 3PL SaaS에서 **필수**로 간주됩니다.
**PackFlow에 없거나 미완성인 항목을 식별하고, 구현 우선순위를 매겨주세요.**

| # | MUST-HAVE 기능 | PackFlow 현황 | 비고 |
|---|---------------|-------------|------|
| 1 | 외부 주문 수신 API | X (스텁만) | 마켓플레이스 자동 수집 필수 |
| 2 | API 인증 (OAuth2/API Key) | X | |
| 3 | 웹훅 (상태 변경 알림) | X | |
| 4 | 캐리어(택배사) 연동 | X | CJ대한통운/로젠/한진 등 |
| 5 | 자동 송장 등록 | X | |
| 6 | 고객사 포탈: 정산서 조회 | X | |
| 7 | 고객사 포탈: 주문 등록 | X | |
| 8 | 고객사 포탈: 입고 요청 | X | |
| 9 | 보관비 자동 계산 트리거 | △ | 함수 있음, 스케줄러 없음 |
| 10 | 정산서 PDF/이메일 | X | |
| 11 | 리포팅/분석 대시보드 | △ | 기본 KPI만 |
| 12 | 모바일 최적화 | △ | 반응형이나 네이티브 앱 X |
| 13 | 사이클 카운트 | X | |
| 14 | 과금 수동 등록/수정/삭제 | X | |
| 15 | 반품 워크플로 자동화 | △ | 기록만, 자동 재입고 규칙 X |

### 6.2 아키텍처 검토 포인트

1. **views.py 비대화**: operator/ 포탈이 5개 파일로 분리되었지만, 각 파일이 200~300줄. 추가 분리가 필요한가?
2. **Service Layer**: 순수 함수 설계 (클래스 없이 repo를 인자로 받음) — DI 패턴으로서 적절한가?
3. **과금 훅의 try/except pass**: 과금 실패가 핵심 업무를 차단하지 않도록 설계. 사일런트 실패 vs 로깅 필요성?
4. **year_month TEXT 필드**: '2026-03' 형식. DATE 타입 대비 트레이드오프?
5. **FK 제약 부재**: Supabase REST API 특성상 FK 강제가 어려움. 대안?
6. **DemoProxy**: Supabase 미연결 시 더미 데이터 반환. 프로덕션 안전성?
7. **테넌트 격리**: BaseRepository에서 operator_id 자동 필터. SQL 인젝션/우회 가능성?

### 6.3 데이터 모델 검토

1. **shipments 단일 테이블**: normal/return/transfer를 하나로 통합. 별도 테이블 분리가 나은가?
2. **client_rates**: 정액(fixed)/정률(rate) 구분만. 구간별/볼륨별 요금은?
3. **client_invoices UNIQUE(operator_id, client_id, year_month)**: 수정분/추가 인보이스 처리?
4. **inventory_stock**: UNIQUE(sku_id, location_id, lot_number) — 같은 SKU 다른 lot이 같은 위치에?

### 6.4 경쟁력 강화 제안 요청

글로벌 3PL SaaS(Extensiv, ShipHero, Logiwa, Deposco 등)와 비교하여:

1. **단기(1~2개월)** 내 반드시 추가해야 할 기능은?
2. **중기(3~6개월)** 로드맵에 넣어야 할 기능은?
3. **장기(6개월+)** AI/자동화 관점에서 준비할 것은?
4. **한국 시장 특화**: 국내 마켓플레이스(네이버/쿠팡/11번가) 연동, 국내 택배사, 세금계산서 등에서 추가로 고려할 점은?
5. **SaaS 과금 모델**: PackFlow 자체의 운영사 대상 과금 (billing_plans) 설계가 적절한가? Extensiv/Logiwa의 모델과 비교 검토

### 6.5 보안/안정성

1. 엑셀 업로드: 파일 크기 제한은 50MB이나 악성 파일 검증 없음
2. api_skus_by_client: 다른 operator의 client 데이터 접근 가능성
3. 과금 금액: client-side에서 amount 변경 가능 여부
4. 세션 관리: 24시간 유효, 동시 로그인 제한 없음
5. CSRF: 현재 미적용 (Flask-WTF 미사용)

---

## Part 7. 현재 미구현 로드맵 (내부 계획)

- [ ] 외부 주문 수신 API (마켓플레이스 자동 수집)
- [ ] 캐리어 연동 (CJ대한통운/로젠/한진 송장 자동 등록)
- [ ] 보관비 월말 일괄 계산 스케줄러
- [ ] 패킹 화면 부자재 입력 → record_packing_fee 연결
- [ ] 정산서 PDF 다운로드 / 이메일 발송
- [ ] 과금 수동 등록/수정/삭제 UI
- [ ] 반품출고 자동 재입고 규칙
- [ ] 클라이언트 포탈: 정산서 조회, 주문 등록, 입고 요청
- [ ] 리포팅 강화 (풀필먼트 정확도, 처리시간, 재고 회전율)
- [ ] 모바일 네이티브 앱 (또는 PWA)

---

## 부록: 파일 구조

```
3pl/
├── app.py                          # Flask 앱 팩토리
├── config.py                       # Dev/Prod 설정
├── models.py                       # User, 역할(13), 메뉴(18), 5개 메뉴그룹
├── db_utils.py                     # get_repo() + DemoProxy
├── auth.py                         # 로그인/로그아웃
├── wsgi.py                         # WSGI 진입점
├── Dockerfile                      # Docker 배포
├── render.yaml                     # Render 배포 설정
│
├── blueprints/
│   ├── api/views.py                # REST API v1 (3 routes)
│   ├── client/views.py             # 고객사 포탈 (4 routes)
│   ├── operator/
│   │   ├── views.py                # 대시보드/과금/사용자 (4 routes)
│   │   ├── order_views.py          # 주문/출고 (6 routes)
│   │   ├── inventory_views.py      # 재고/입고/SKU (6 routes)
│   │   ├── client_views.py         # 고객사/요금/정산 (14 routes)
│   │   └── warehouse_views.py      # 창고/구역 (5 routes)
│   └── packing/views.py            # 패킹센터 (6 routes)
│
├── repositories/                   # Data Access (12 repos)
│   ├── base.py                     # BaseRepository (CRUD + tenant filter)
│   ├── client_repo.py              # 고객사
│   ├── order_repo.py               # 주문/출고/보류/상태로그
│   ├── inventory_repo.py           # SKU/재고/이력/예약
│   ├── warehouse_repo.py           # 창고/구역/로케이션
│   ├── picking_repo.py             # 피킹리스트/항목
│   ├── packing_repo.py             # 패킹작업/영상
│   ├── billing_repo.py             # 플랫폼 과금
│   ├── client_rate_repo.py         # 고객사 요금표
│   ├── client_billing_repo.py      # 고객사 과금/정산
│   ├── client_marketplace_repo.py  # 마켓플레이스 API 인증
│   └── user_repo.py                # 사용자
│
├── services/                       # Business Logic (8 services)
│   ├── inventory_service.py        # 2-Phase 재고 (예약/커밋/롤백)
│   ├── warehouse_service.py        # 입고/출고 처리
│   ├── picking_service.py          # 피킹리스트 자동 생성 (FIFO)
│   ├── scan_validator.py           # 바코드 스캔 검증 (오출고 차단)
│   ├── shipment_guard.py           # 출고 차단 검증
│   ├── client_billing_service.py   # 자동 과금 엔진 (21 프리셋)
│   ├── billing_service.py          # 플랫폼 과금
│   └── tz_utils.py                 # KST 시간대
│
├── migrations/                     # SQL 스키마 (7 files)
│   ├── 001_initial_schema.sql      # 기본 테이블 (operators~shipments)
│   ├── 002_test_data.sql           # 테스트 데이터
│   ├── 003_client_rates.sql        # 고객사 요금표
│   ├── 004_wms_core.sql            # 보류/피킹/재고예약
│   ├── 005_client_marketplace.sql  # 마켓플레이스 인증
│   ├── 006_outbound_enhanced.sql   # 반품/창고이동
│   └── 007_billing_enhanced.sql    # 과금/정산 테이블
│
├── templates/                      # 29 HTML templates
│   ├── base.html, login.html
│   ├── landing/index.html
│   ├── operator/ (19개)
│   ├── client/ (4개)
│   └── packing/ (6개)
│
└── static/css/app.css
```

---

**이 문서를 기반으로 PackFlow의 완성도를 글로벌/국내 3PL SaaS 기준에서 평가하고, 구체적인 개선 사항과 우선순위를 제안해주세요.**
