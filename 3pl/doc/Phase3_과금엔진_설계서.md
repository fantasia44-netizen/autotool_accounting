# PackFlow 과금 엔진 v2.0 설계서 (통합본)

> **목적**: 현재 고정단가 기반의 단순 과금을 **조건별 공식 기반 과금**으로 확장 및 엣지 케이스 방어
> **작성일**: 2026-03-19
> **업데이트**: 단가 이력 관리, 체적/반품 변수, 배치 프로세스 및 안전장치 보완 적용 (Gemini 리뷰 반영)

---

## 1. 현재 과금 구조의 한계

```
현재: client_rates
  fee_name = "출고작업비"
  fee_type = "fixed"
  amount = 300          ← 무조건 300원/건

필요: 조건별 과금
  포장형태가 단품이면 → 300원
  포장형태가 합포장이면 → 300원 + (추가품목 × 100원)
  포장형태가 이종합포장이면 → 500원
  중량 5kg 초과 시 → 초과 kg당 200원 추가
```

---

## 2. 과금 엔진 v2.0 구조 및 스키마

### 2-1. 요금표 확장 스키마 (이력 관리 포함)

```sql
-- client_rates 테이블 확장
ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    conditions JSONB DEFAULT '{}';
    -- 조건 정의 (언제 이 요금이 적용되는지)

ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    formula TEXT DEFAULT NULL;
    -- 계산 공식 (단순 금액이 아닌 공식 기반 계산)

ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    applies_to TEXT DEFAULT 'all';
    -- 적용 대상: 'all', 'single', 'multi', 'mixed'

-- [v2.0 보강] 단가 이력 관리 및 방어 로직용 컬럼 추가
ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    valid_from TIMESTAMPTZ DEFAULT NOW();
    -- 요금 적용 시작일

ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    valid_to TIMESTAMPTZ DEFAULT '2099-12-31 23:59:59';
    -- 요금 적용 종료일

ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    min_amount NUMERIC DEFAULT 0;
    -- 수식 결과 최소 보장 금액 (음수 과금 방지)
```

### 2-2. conditions JSONB 구조

```json
{
  "pack_type": "single",              // 단품/합포/이종 조건
  "weight_min_g": 0,                  // 최소 중량 (g)
  "weight_max_g": 5000,               // 최대 중량 (g)
  "item_count_min": 1,                // 최소 품목수
  "item_count_max": 1,                // 최대 품목수
  "storage_temp": "frozen",           // 보관온도 조건
  "sku_category": "식품",             // SKU 카테고리 조건
  "delivery_region": "제주",          // 배송지역 조건
  "time_slot": "dawn",               // 시간대 (새벽배송 등)
  "event_type": "return_inbound",     // [추가] 입고 유형 (반품 등)
  "cs_requires_repacking": true       // [추가] 양품화(재포장) 작업 여부
}
```

### 2-3. formula 계산 공식 및 변수

**핵심 변수 목록:**

| 변수 | 설명 |
|------|------|
| `{qty}` | 수량 |
| `{item_count}` | 주문 내 품목수 |
| `{pallet_count}` | 파레트 수량 |
| `{days}` | 보관일수 |
| `{base_amount}` | 기본금액 (amount 필드) |
| `{net_weight_kg}` | 순수 상품 이론적 총 중량 |
| `{gross_weight_kg}` | 상품 + 박스/부자재 실측 총 중량 |
| `{volumetric_weight_kg}` | 체적 중량 (가로×세로×높이 / 체적계수) |
| `{chargeable_weight_kg}` | 최종 청구 중량 = max(gross, volumetric) |

**예시 공식:**
```
"300"                                    → 고정 300원
"{base_amount} * {qty}"                  → 단가 × 수량
"{base_amount} + ({item_count} - 1) * 100" → 기본 + 추가품목당 100원
"3500 + max(0, ceil({chargeable_weight_kg} - 5)) * 500" → 5kg 초과 체적/실측 중 큰 값
"{base_amount} * {pallet_count} * {days}" → 단가 × 파레트 × 일수
```

---

## 3. 1업체 과금 구조 예시

### 3-1. 출고비 (포장형태별)

| 항목 | 조건 | 단가 | 공식 |
|------|------|------|------|
| 출고작업비(단품) | pack_type=single | 300원/건 | `300` |
| 출고작업비(합포) | pack_type=multi | 300원 + 추가품목당 100원 | `300 + ({item_count} - 1) * 100` |
| 출고작업비(이종합포) | pack_type=mixed | 500원/건 | `500` |

### 3-2. 운송비 (조건별)

| 항목 | 조건 | 공식 |
|------|------|------|
| 기본/중량택배비 | - | `3500 + max(0, ceil({chargeable_weight_kg} - 5)) * 500` |
| 제주추가비 | region=제주 | `3000` |
| 도서산간추가비 | region=도서 | `5000` |

### 3-3. 부자재비

| 항목 | 공식 |
|------|------|
| 박스(소) | `{qty} * 500` |
| 박스(중) | `{qty} * 800` |
| 박스(대) | `{qty} * 1200` |
| 아이스팩 | `{qty} * 300` |
| 드라이아이스 | `{qty} * 500` |
| 완충재 | `{qty} * 100` |
| 테이프 | `{qty} * 50` |

### 3-4. 입고비

| 항목 | 공식 |
|------|------|
| 입고검수비 | `{qty} * 50` |
| 파레트 하차비 | `{pallet_count} * 5000` |
| 상차비 | `{pallet_count} * 3000` |
| 반품입고/재포장비 | `1500 + {item_count} * 500` |

### 3-5. 보관비 (일할 계산)

| 항목 | 조건 | 공식 |
|------|------|------|
| 일반보관비 | temp=ambient | `{pallet_count} * 3000` (일당) |
| 냉장보관비 | temp=cold | `{pallet_count} * 5000` (일당) |
| 냉동보관비 | temp=frozen | `{pallet_count} * 7000` (일당) |

---

## 4. 과금 엔진 처리 플로우

### 4-1. 동기 처리 (출고/입고 이벤트)

```
1. 주문/입고 정보 수집
   - pack_type: single/multi/mixed
   - item_count: 품목수
   - chargeable_weight_kg: max(실측, 체적)
   - delivery_region: 배송지역

2. 고객사 요금표 조회
   - valid_from ~ valid_to 범위 내 활성 요금만

3. 각 요금항목에 대해:
   a. conditions 매칭 체크
   b. 조건 불일치 → 스킵
   c. 조건 일치 → formula 안전 계산
   d. formula 없으면 → amount × qty (기존 방식)
   e. min_amount 이하 → min_amount로 보정

4. 과금 로그 기록 (client_billing_logs)
```

### 4-2. 비동기 배치 처리 (보관비)

```
보관비는 매일 재고가 변동되므로 일할 과금 배치로 처리:

1. 자정(00:00) 스냅샷
   - 화주/SKU별 총재고량, 파레트/CBM 수량 기록
   - daily_inventory_snapshot 테이블

2. 새벽 배치 (02:00)
   - 스냅샷 데이터 → 온도대별 보관비 산정
   - client_billing_logs에 일별 INSERT

3. 월말 정산서
   - 일별 보관비 합산 → 카테고리별 소계
```

---

## 5. 수식 엔진 (Formula Engine) 안전장치

### 평가 함수

```python
def evaluate_formula(formula_str, context_vars, min_amount=0):
    if not formula_str:
        return max(
            context_vars.get('base_amount', 0) * context_vars.get('qty', 1),
            min_amount
        )

    try:
        # 1. 안전한 수식 파서 (eval 절대 금지)
        raw_result = safe_math_parser(formula_str, context_vars)

        # 2. 음수 및 최소금액 방어
        return max(raw_result, min_amount)

    except VariableMissingError as e:
        # 누락 시 DLQ 이동 및 수동 처리 유도
        log.error(f"과금 실패: 필수 변수 누락 {e}")
        move_to_dlq(context_vars)
        return 0
```

### 보안 규칙
- **eval() 절대 금지** → 안전한 수식 파서 사용
- 허용 연산: `+, -, *, /, ceil, floor, min, max`
- 허용 변수: 사전 정의된 변수만
- 잘못된 공식 → 에러 로그 + DLQ 이동 (과금 중단 아님)

### 호환성
- `formula = NULL` → 기존 방식 (amount × qty) 유지
- `conditions = {}` → 무조건 적용 (기존 동작)
- 기존 데이터/요금표 **100% 하위 호환**

### 감사추적
- 과금 시 적용된 조건과 공식을 `billing_log.memo`에 기록
- 정산서에 공식 근거 표시 가능

---

## 6. GPT 리뷰 반영 — 현장 운영자 중심 설계

> "지금은 강력하지만 못 쓰는 시스템 → 누구나 쓰는 시스템으로 바꿔야 한다"

### 6-1. 요금 템플릿 시스템 (formula 숨기기)

```
운영자가 보는 UI:              내부 처리:
┌────────────────────┐        ┌─────────────────────────┐
│ [v] 단품 출고 300원 │   →    │ formula: "300"           │
│ [v] 합포 출고 기본300│  →    │ formula: "300+({item_    │
│     + 추가품목 100원│        │  count}-1)*100"          │
│ [v] 중량 추가 5kg초과│  →    │ conditions: weight>5000  │
│     kg당 500원      │        │ formula: "ceil(..)*500"  │
│ [v] 제주 추가 3000원│   →    │ conditions: region=제주  │
└────────────────────┘        └─────────────────────────┘

→ formula는 내부에서만 사용
→ UI에서는 분해된 구조로 제공 (기본금액 + 추가금액 + 조건)
```

### 6-2. 조건 우선순위 + 스태킹

```sql
ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    priority INT DEFAULT 100;    -- 낮을수록 우선 (기본=100)

ALTER TABLE client_rates ADD COLUMN IF NOT EXISTS
    is_stackable BOOLEAN DEFAULT TRUE;  -- 다른 조건과 중첩 적용 여부
```

```
예시: 제주 + 중량초과 주문
  제주추가비   (priority=10, stackable=TRUE)  → 적용
  중량추가비   (priority=20, stackable=TRUE)  → 적용
  → 둘 다 적용 (스태킹)

예시: VIP 할인 + 일반 출고비
  VIP 할인출고비 (priority=1, stackable=FALSE) → 적용
  일반 출고비    (priority=100)                 → 스킵 (VIP가 우선)
```

### 6-3. Speed / Precision Billing 분리

```
속도모드 (Speed Billing):
  → 조건 체크 최소화
  → 단순 고정가 우선 적용
  → formula 없는 항목만 즉시 계산
  → 복잡한 조건 과금은 billing_queue로 후처리

안정모드 (Precision Billing):
  → conditions 전체 매칭
  → formula 완전 계산
  → 즉시 과금
```

### 6-4. 이벤트 기반 과금 (상태 변경 추적)

```
출고 생명주기별 과금:
  outbound_created    → 과금 예약 (임시)
  outbound_confirmed  → 과금 확정
  outbound_cancelled  → 과금 취소 (역분개)
  outbound_modified   → 차액 조정

→ 출고 수정/취소 시에도 과금이 꼬이지 않음
```

### 6-5. 고객사 Override (예외 요금)

```json
// client_rates에 override 조건 추가
{
  "conditions": {
    "sku_id": 123,           // 특정 SKU 무료
    "override_amount": 0
  }
}

// 또는 고객사별 할인율
{
  "conditions": {},
  "formula": "{base_amount} * 0.9"   // 10% 할인
}
```

### 6-6. 입력값 검증 (Sanity Check)

```python
def sanity_check(context):
    """과금 전 입력값 이상 탐지"""
    if context.get('weight_kg', 0) > 100:
        log.warning('비정상 중량: %s kg', context['weight_kg'])
    if context.get('item_count', 0) > 50:
        log.warning('비정상 품목수: %s', context['item_count'])
    if context.get('qty', 0) <= 0:
        raise ValueError('수량이 0 이하')
```

### 6-7. 손익 분석 대시보드

```
고객사별 수익:
  매출 (과금 합계) - 비용 (인건비+택배+부자재) = 순이익

SKU별 수익:
  출고 건수 × 건당 수익 = SKU별 기여도

적자 고객 분석:
  보관비 > 출고비 → 재고 회전율 낮은 화주 경고
```

---

## 7. 구현 계획

### Phase 1: DB 스키마 확장
- client_rates에 conditions, formula, applies_to, valid_from/to, min_amount 추가
- 기존 요금항목 100% 하위 호환

### Phase 2: 과금 엔진 코어
- `evaluate_formula(formula, variables, min_amount)` 함수
- `match_conditions(conditions, context)` 함수
- `calculate_fee(rate, context)` 통합 함수
- 기존 record_*_fee 함수들을 엔진 호출로 교체
- 보관비 일할 계산용 자정 스냅샷 배치 스케줄러

### Phase 3: 요금표 관리 UI
- 조건 설정 UI (포장형태, 중량범위, 지역 등)
- 공식 입력 + 시뮬레이션 (금액 미리보기)
- 프리셋 템플릿 (기본 3PL 요금표)

### Phase 4: 정산서 고도화
- 카테고리별 소계 + 조건별 상세
- 과금 공식 투명성 (어떤 조건으로 얼마가 계산됐는지)

---

---

## 8. 고객사별 출고 등급 시스템 (사이즈 자동 판별)

### 8-1. DB 스키마

```sql
-- 고객사별 출고 등급 구간 설정 (최대 6단계)
CREATE TABLE IF NOT EXISTS client_shipping_tiers (
    id BIGSERIAL PRIMARY KEY,
    operator_id BIGINT NOT NULL REFERENCES operators(id),
    client_id BIGINT NOT NULL REFERENCES clients(id),
    tier_name TEXT NOT NULL,           -- 소형/중형/중대형/대형/특대형/파레트
    tier_order INT NOT NULL,           -- 정렬순서 (1~6)
    qty_min INT NOT NULL,              -- 수량 구간 시작
    qty_max INT NOT NULL,              -- 수량 구간 끝
    box_type TEXT NOT NULL,            -- 박스 종류명 (아이스박스(소), 스티로폼(대) 등)
    ice_pack_count INT DEFAULT 0,      -- 아이스팩 수량
    dry_ice_count INT DEFAULT 0,       -- 드라이아이스 수량
    cushion_count INT DEFAULT 0,       -- 완충재 수량
    tape_count INT DEFAULT 1,          -- 테이프 수량
    extra_materials JSONB DEFAULT '{}',-- 추가 부자재 {name: qty}
    work_fee_name TEXT,                -- 연결할 작업비 요금항목명
    courier_fee_name TEXT,             -- 연결할 택배비 요금항목명
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shipping_tiers_client
    ON client_shipping_tiers(client_id, tier_order);
```

### 8-2. 예시 데이터 (A업체)

| 등급 | 수량 | 박스 | 아이스팩 | 드라이 | 완충재 | 작업비 |
|------|------|------|---------|--------|--------|--------|
| 소형 | 1~3 | 아이스박스(소) | 2 | 1 | 1 | 기본작업비 |
| 중형 | 4~8 | 아이스박스(중) | 3 | 2 | 2 | 기본작업비(중형) |
| 중대형 | 9~15 | 아이스박스(대) | 4 | 3 | 3 | 기본작업비(대형) |
| 대형 | 16~25 | 스티로폼(대) | 6 | 4 | 4 | 기본작업비(대형) |
| 특대형 | 26~40 | 스티로폼(특대) | 8 | 5 | 5 | 기본작업비(특대) |
| 파레트 | 41~ | 파레트포장 | 별도 | 별도 | 별도 | 파레트작업비 |

### 8-3. 주문접수 자동 판별 플로우

```
주문 접수 (총 수량 12개)
  ↓
client_shipping_tiers 조회 (해당 고객사)
  ↓
qty_min ≤ 12 ≤ qty_max → "중대형" 매칭
  ↓
자동 세팅:
  - box_type: 아이스박스(대)
  - 아이스팩: 4개
  - 드라이아이스: 3개
  - 완충재: 3개
  ↓
과금 엔진 호출:
  - 기본작업비(대형) → client_rates에서 조회
  - 부자재비: 아이스박스(대)×1 + 아이스팩×4 + 드라이×3 + 완충재×3
  - 택배비: 중량/사이즈별 자동
```

### 8-4. 검증 포인트

```
송장 자동수집 시:
  1. 주문 수량 확인
  2. 등급 자동 판별
  3. 부자재 수량 계산
  4. 실제 사용량과 대조 (패킹 시 스캔된 부자재와 비교)
  5. 차이 발생 시 경고 → 수동 확인
```

---

## 9. 다음 단계 (과금 외)

### 자동 주문수집 (통합툴에서 가져올 것)
- 채널별 API 연동 (스마트스토어, 쿠팡, 옥션G마켓)
- 옵션마스터 매칭 시스템
- 자동 주문접수 → 3PL 주문테이블 연동

### 송장 처리
- 자동 송장번호 생성
- 송장등록 엑셀 다운로드
- 택배사 API 연동 (CJ대한통운, 롯데 등)
- 송장 일괄등록 처리

### 피킹 자동화
- 송장 출력 시 자동 피킹리스트 생성
- 구역별/창고별 피킹 분류
- 작업자 할당 자동화
