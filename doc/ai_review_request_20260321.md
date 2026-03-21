# AI 검토 요청서 — AutoTool + PackFlow 통합 리뷰

> **요청일**: 2026-03-21
> **요청자**: Danny (개발자, 1인 개발)
> **대상 AI**: GPT-4o / Gemini 2.5 Pro
> **목적**: 두 시스템의 아키텍처, 보안, 코드 품질, 설계 방향에 대한 교차 검토 및 개선 제안

---

## 검토 배경

1인 개발자가 두 개의 Flask+Supabase 시스템을 동시에 개발/운영 중입니다:
- **AutoTool**: 이유식 제조업체 전용 ERP/WMS (실운영 중, Render 배포)
- **PackFlow**: 3PL 물류대행 전용 SaaS (클로즈드 베타 준비 중)

두 시스템 모두 Supabase를 DB로 사용하며, ORM 없이 REST API로 직접 통신합니다.
일주일간의 대규모 업데이트 후 중간 점검이 필요합니다.

---

## 검토 요청 항목

### 1. 아키텍처 검토

**AutoTool (ERP/WMS)**
```
규모: Python 46,700줄 / 337 라우트 / 88 템플릿
구조: app.py → blueprints(38) → services(45) → db_supabase.py(5,051줄, 255 메서드)
특징: 단일 DB 파일에 모든 쿼리 집중, ORM 없음
```

**PackFlow (3PL SaaS)**
```
규모: Python 11,200줄 / 115 라우트 / 63 템플릿
구조: app.py → blueprints(8) → services(17) → repositories(15) → Supabase
특징: Repository 패턴 채택, 소프트삭제+감사로그 내장
```

**검토 질문:**
1. AutoTool의 db_supabase.py(5,051줄)가 God Object 안티패턴에 해당하는가? Repository 패턴으로 분리하면 어떤 구조가 적절한가?
2. PackFlow의 Repository→Service→Blueprint 3계층 구조는 적절한가? 과도한 추상화는 아닌가?
3. 두 시스템 간 코드 공유가 가능한 부분이 있는가? (인증, DB 연결, 유틸리티 등)
4. Supabase를 ORM 없이 사용하는 것의 장단점과 리스크는?

---

### 2. 보안 검토 (P0 이슈 집중)

**PackFlow 보안 리뷰(2026-03-18) 에서 발견된 P0 이슈:**

#### 이슈 1: 멀티테넌트 격리 누락
```python
# base.py — _update() 내 before-snapshot
current = self.client.table(table).select("*").eq("id", id_val).single().execute()
# 문제: operator_id 필터 없이 id만으로 조회 → 타 테넌트 데이터 접근 가능
```

#### 이슈 2: API 인증 없음
```python
# api/views.py
@api_bp.route('/api/v1/orders', methods=['POST'])
def create_order():
    # TODO: API key 인증 + 주문 생성
    return jsonify({'status': 'received'}), 201
# 문제: 완전 공개 상태, 아무나 주문 생성 가능
```

#### 이슈 3: 재고 이중 커밋
```python
# inventory_service.py — commit_stock()
# RPC fn_commit_stock은 멱등하나, UI에서 try/except pass로 예외 무시
# 동시 호출 시 이중 차감 가능성
```

**검토 질문:**
1. before-snapshot 테넌트 격리 — 가장 안전한 수정 방법은?
2. API 인증 — API Key + HMAC vs JWT vs OAuth2 중 3PL SaaS에 적합한 방식은?
3. 재고 이중 커밋 — Supabase RPC 레벨에서 멱등성을 보장하는 패턴은?
4. AutoTool에도 동일한 보안 패턴이 존재하는가? (db_supabase.py 기준)

---

### 3. 과금 엔진 v2.0 검토

PackFlow의 핵심 경쟁력인 과금 엔진을 검토해 주세요.

**현재 구현 (billing_engine.py, 394줄):**
```python
# 조건별 공식 기반 과금
# 예시 요금 룰:
{
    "condition": {"pack_type": "single"},
    "formula": "{base_amount}",
    "variables": {"base_amount": 300}
}
{
    "condition": {"pack_type": "multi"},
    "formula": "{base_amount} + ({item_count} - 1) * {extra_per_item}",
    "variables": {"base_amount": 300, "extra_per_item": 100}
}

# 안전한 수식 평가기 (eval 대신):
DANGEROUS_KEYWORDS = ['import', 'exec', 'eval', 'compile', '__', 'open', 'os', 'sys']
```

**DB 스키마 (020_billing_engine_v2.sql):**
- billing_rate_templates: 21개 프리셋 (입고/출고/보관/택배/부자재/반품/부가서비스)
- client_rates: 고객별 커스텀 요금
- billing_logs: 과금 이력 (dedupe_key로 멱등성)

**검토 질문:**
1. 수식 평가기의 보안 — 키워드 블랙리스트 방식이 충분한가? 더 안전한 대안은?
2. 과금 템플릿 21개 프리셋이 3PL 시장을 충분히 커버하는가?
3. 역분개(credit note) 로직이 미구현인데, 권장 패턴은?
4. 대량 과금 배치 처리 시 성능 최적화 방안은?

---

### 4. 듀얼모드 풀필먼트 검토

**구현 내용:**
```
일반모드(Precision): 주문별 피킹 → 주문별 패킹 → 개별 검수
속도모드(Speed):     상품별 총량 피킹 → 1-Touch 패킹 → 일괄 검수

모드 판별: 전체 SKU가 speed 가능해야 speed 모드
          하나라도 정밀 필요하면 전체 주문이 precision으로 강등
```

**검토 질문:**
1. 모드 강등 규칙이 너무 보수적인가? 부분 분리(일부 speed, 일부 precision) 전략은?
2. 속도모드에서 오배송 방지를 위한 추가 검증이 필요한가?
3. KPI 지표(UPH, 처리시간)가 3PL 업계 표준과 비교해 적절한가?

---

### 5. AutoTool 최근 변경 검토

**채널 레지스트리 범용화 (channel_config.py → 559줄):**
```python
# 이전: 채널명 하드코딩 (if channel == '쿠팡': ...)
# 이후: 레지스트리 패턴 (CHANNEL_REGISTRY[channel].platform_type)
# 신규 채널 추가 시 레지스트리에 등록만 하면 됨
```

**API 주문수집 (orders_api.py → 317줄):**
```python
# 마켓플레이스 API로 주문 자동 수집 → DB 저장 → 재고 차감
# 실패 시 자동 롤백 (재고 원복)
# 채널: 쿠팡, 네이버, 카페24
```

**검토 질문:**
1. 채널 레지스트리 — 더 나은 확장 패턴이 있는가? (플러그인, 동적 로딩 등)
2. API 주문 수집 + 재고 차감 — 트랜잭션 일관성은 어떻게 보장하는가? Supabase에서 ACID는?
3. 마켓플레이스 API 호출 실패 시 재시도/서킷브레이커 패턴이 필요한가?

---

### 6. DB 안정성 검토

**AutoTool db_supabase.py (5,051줄):**
```python
# 연결 끊김 감지 패턴 11가지:
PATTERNS = ['RemoteProtocolError', 'ConnectError', 'ConnectionTerminated',
            'TimeoutException', 'server disconnected', 'connection reset',
            'statement timeout', '57014', 'canceling statement', ...]

# 재시도: 3회 + backoff (1초→2초)
# 캐시: option_cache(30분), permission_cache(10분), sidebar_cache(5분), price_cache
# 페이지네이션: 1000행/페이지
```

**검토 질문:**
1. Supabase 무료 플랜의 유휴 연결 끊김 — 현재 대응이 충분한가?
2. 인메모리 캐시 대신 Redis 등 외부 캐시가 필요한 시점은?
3. 5,051줄 단일 파일의 유지보수성 — 분리한다면 어떤 기준으로?

---

### 7. 테스트 전략 제안 요청

두 시스템 모두 자동화 테스트가 거의 없습니다 (AutoTool 0건, PackFlow 3건).

**현실적 제약:**
- 1인 개발, 테스트 작성에 할애할 시간 제한적
- Supabase 무료 플랜 → 별도 테스트 DB 구성 어려움
- CI/CD 미구성 상태

**검토 질문:**
1. 1인 개발자가 가장 효과적으로 시작할 수 있는 테스트 전략은?
2. Supabase를 모킹하는 가장 실용적인 방법은?
3. 최소한의 테스트로 최대 안전성을 확보하는 "핵심 경로" 테스트 목록을 제안해 주세요
4. GitHub Actions로 가장 간단하게 CI를 구성하는 방법은?

---

### 8. 로드맵/우선순위 제안 요청

**현재 상황:**
- AutoTool: 80% 완성, 실운영 중
- PackFlow: 70% 완성, 클로즈드 베타 준비 중
- 1인 개발, 주 40~60시간 투입 가능
- 목표: PackFlow 3개월 내 유료 베타 출시

**검토 질문:**
1. 남은 30%를 어떤 순서로 구현해야 가장 빨리 유료 출시할 수 있는가?
2. MVP에서 과감하게 빼도 되는 기능은?
3. 1인 개발의 현실적 한계를 감안한 "최소 안전성" 기준은?
4. AutoTool 유지보수 vs PackFlow 신규개발 — 시간 배분 비율 권장은?

---

## 참고 문서

| 문서 | 경로 | 설명 |
|------|------|------|
| AutoTool 진행도 | `autotool/doc/autotool_progress_20260321.md` | 모듈별 상세 현황 |
| PackFlow 진행도 | `3pl/doc/packflow_progress_20260321.md` | 모듈별 상세 현황 |
| 과금엔진 설계서 | `3pl/doc/Phase3_과금엔진_설계서.md` | v2.0 설계 |
| 현장화면 설계서 | `3pl/doc/Phase4_현장화면분할_설계서.md` | 5모드 분할 |
| 보안 검토서 | `3pl/docs/security_review_20260318.md` | P0~P2 이슈 |
| 아키텍처 문서 | `3pl/docs/packflow_architecture.md` | 전체 구조 |
| 축산물 MES 설계 | `autotool/doc/축산물_MES_설계서.md` | API 검증 완료 |

---

## 응답 형식 요청

각 항목에 대해 다음 형식으로 응답해 주세요:

```
### [항목번호] [제목]

**현재 상태 평가**: (양호/주의/위험)
**개선 제안**: (구체적 코드 또는 아키텍처 변경안)
**우선순위**: (P0 즉시 / P1 2주 / P2 1개월 / P3 백로그)
**예상 공수**: (시간 단위)
```

특히 "이렇게 바꿔라"는 구체적인 코드 예시를 포함해 주시면 바로 적용할 수 있어 매우 유용합니다.

---

> 이 문서는 GPT-4o와 Gemini 2.5 Pro에 동시에 제공되어 교차 검토를 받습니다.
> 두 AI의 의견이 다른 경우 각각의 근거를 비교하여 최종 결정합니다.
