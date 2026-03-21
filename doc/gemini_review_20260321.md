# Gemini 2.5 Pro 검토 결과 — 2026-03-21

> **검토 대상**: AutoTool + PackFlow 통합 리뷰
> **검토자**: Gemini 2.5 Pro
> **요청서**: `doc/ai_review_request_20260321.md`

---

## 요약 판정표

| # | 항목 | 평가 | 우선순위 | 예상 공수 |
|---|------|------|----------|-----------|
| 1 | 아키텍처 (AutoTool God Object) | 주의 | P1 2주 | 15시간 |
| 2 | 보안 P0 이슈 3건 | 위험 | P0 즉시 | 20시간 |
| 3 | 과금 엔진 수식 보안 | 주의 | P1 2주 | 12시간 |
| 4 | 듀얼모드 풀필먼트 | 양호 | P2 1개월 | 15시간 |
| 5 | AutoTool 최근 변경 | 양호 | P2 1개월 | 8시간 |
| 6 | DB 안정성 | 주의 | P2 1개월 | 6시간 |
| 7 | 테스트 전략 | 위험 | P0 즉시 | 10시간 |
| 8 | 로드맵/우선순위 | — | P0 즉시 | 2시간 |

**총 예상 공수: 88시간 (~2.5주 풀타임)**

---

## 1. 아키텍처 검토

**평가: 주의** (AutoTool God Object 심각, PackFlow 양호)

### 제안 1-1: AutoTool db_supabase.py Mixin 분리
- 5,051줄 God Object → Mixin 패턴으로 **파일만 분리** (전면 리팩토링 위험 회피)

```python
# db_orders.py
class OrderDBMixin:
    def get_orders(self): ...

# db_supabase.py
class SupabaseDB(OrderDBMixin, InventoryDBMixin):
    def __init__(self):
        # 기본 클라이언트 초기화
```

### 제안 1-2: PackFlow에 Pydantic 모델 도입
- ORM 없는 상태에서 타입 안정성 확보
- Service 계층 입출력에 Pydantic 적용 → 데이터 검증 레이어

**P1 2주 / 15시간**

---

## 2. 보안 검토 (P0)

**평가: 위험** (상용화 불가 수준)

### 제안 2-1: 멀티테넌트 격리 — Supabase RLS 활성화
- 앱 코드만 의존 → 휴먼 에러로 타사 데이터 노출 가능
- 테이블마다 `operator_id` RLS 정책 설정
- API 호출 시 테넌트 JWT/헤더 컨텍스트 강제

### 제안 2-2: API 인증 — API Key + HMAC-SHA256
- 서버-to-서버 연동에는 JWT보다 **정적 키 + 서명 방식**이 표준
- 구현도 훨씬 단순

### 제안 2-3: 재고 이중 커밋 — 낙관적 락(Optimistic Locking)
- `version` 컬럼 추가
- `WHERE id = X AND version = Y` 조건 검사
- UI의 try/except pass 제거

**P0 즉시 / 20시간**

---

## 3. 과금 엔진 v2.0

**평가: 주의** (수식 평가기 보안 취약)

### 제안 3-1: 블랙리스트 → 화이트리스트 파서로 교체
- `eval` 절대 금지
- `ast.literal_eval` 베이스로 사칙연산 노드만 허용
- 또는 `simpleeval` 라이브러리 도입

### 제안 3-2: 역분개 — Append-only 회계 원칙
- 기존 billing_logs 삭제/수정 금지
- 음수(-) 금액의 정정 트랜잭션 Insert
- 합산 시 자동 차감

### 제안 3-3: 대량 과금 — Bulk Insert
- 개별 Insert → 500~1000건 청크 단위 Bulk Insert

**P1 2주 / 12시간**

---

## 4. 듀얼모드 풀필먼트

**평가: 양호** (도메인 특화 설계 훌륭)

### 제안 4-1: 웨이브 분할로 강등 완화
- 전체 강등 대신 **속도모드 웨이브 + 정밀모드 웨이브** 분리
- 동선 완전 분리로 UPH 향상

### 제안 4-2: 속도모드 중량 검증
- 1-Touch 패킹 시 바코드 스캔 생략 → 오배송 위험
- **중량계(Weight Scale) API 연동**
- 이론적 BOM 중량 vs 실제 중량 비교

**P2 1개월 / 15시간**

---

## 5. AutoTool 최근 변경

**평가: 양호** (설계 확장성 개선됨)

### 제안 5-1: 채널 레지스트리 현행 유지
- 현재 규모에서 딕셔너리 기반 충분
- 채널 늘어나면 `entry_points` 플러그인으로 전환

### 제안 5-2: 백그라운드 대사(Reconciliation) 데몬 추가
- API 실패 시 DB 롤백만으로는 일관성 100% 불가
- '처리 중(processing)' 주문을 주기적으로 찾아 정합성 맞추는 데몬

**P2 1개월 / 8시간**

---

## 6. DB 안정성

**평가: 주의** (인메모리 캐시 + 단일 장애점)

### 제안 6-1: 인메모리 캐시 → 인덱싱 고도화
- 스케일아웃 시 데이터 불일치 문제
- Redis 여력 없으면 Supabase 인덱싱 강화 + 캐시 의존도 축소

### 제안 6-2: tenacity 라이브러리 도입
- 커스텀 재시도 → `tenacity` 데코레이터 (Backoff + Jitter 내장)
- 코드 간결화

**P2 1개월 / 6시간**

---

## 7. 테스트 전략

**평가: 위험** (회귀 버그 무방비)

### 제안 7-1: 핵심 로직 2개만 단위 테스트
1. **PackFlow 과금 엔진** (billing_engine.py)
2. **AutoTool 재고 차감** (order_to_stock_service.py)
- UI 테스트는 포기

### 제안 7-2: Supabase 모킹 — requests-mock
- 실제 DB 불필요
- HTTP 요청 가로채서 JSON 응답 반환

### 제안 7-3: GitHub Actions CI — 20줄
```yaml
name: Test
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt pytest requests-mock
      - run: pytest
```

**P0 즉시 / 10시간**

---

## 8. 로드맵/우선순위

### 시간 배분
- **AutoTool**: 10% (크리티컬 버그만)
- **PackFlow**: 90% (유료화 올인)

### 상용화 구현 순서
1. **P0 보안 수정 (2주)** — 고객 데이터 수령 전제조건
2. **고객 포털 완성 (2주)** — "고객사가 직접 볼 수 있는 투명한 대시보드"가 세일즈 포인트
3. **수동 런칭 (MVP 삭감)** — API 웹훅/2FA/세금계산서 연동은 베타 후 구현

### MVP에서 빼도 되는 기능
- API 키 기반 외부 웹훅
- 2FA/MFA
- 복잡한 세금계산서 연동
- 고급 리포팅/분석

### 핵심 메시지
> "일단 런칭하고 초기 고객 1~2개사를 수동으로 밀착 대응하세요"

**P0 즉시 / 2시간 (기획)**

---

## 우선 실행 순서 (Gemini 권장)

| 순서 | 작업 | 기간 | 공수 |
|------|------|------|------|
| 1 | P0 보안 3건 수정 (RLS + API인증 + 낙관적 락) | 2주 | 20h |
| 2 | 핵심 로직 테스트 + CI 구성 | 1주 | 10h |
| 3 | 과금 엔진 수식 파서 교체 + 역분개 | 1주 | 12h |
| 4 | 고객 포털 완성 | 2주 | 20h |
| 5 | AutoTool db_supabase.py Mixin 분리 | 1주 | 15h |
| 6 | 듀얼모드 웨이브 분할 + 중량 검증 | 2주 | 15h |
| 7 | DB tenacity + 백그라운드 대사 | 1주 | 14h |
| **합계** | | **~10주** | **106h** |
