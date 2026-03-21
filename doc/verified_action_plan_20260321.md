# 코드 기반 교차검증 결과 + 실제 액션 플랜 — 2026-03-21

> **목적**: GPT/Gemini가 설계서만 보고 지적한 내용을 실제 코드와 대조하여 진짜 해야 할 것만 추림
> **검증 방법**: Claude가 실제 소스코드 라인 단위로 확인

---

## 1. AI 지적 vs 실제 코드 — 교차검증표

### PackFlow (3PL)

| AI 지적 | 등급 | 실제 코드 확인 결과 | 실제 등급 | 조치 |
|---------|------|---------------------|-----------|------|
| 멀티테넌트 before-snapshot 격리 누락 | P0 | **이미 수정됨** ✅ `_update()`, `_delete()` 모두 `_apply_tenant_filter()` 적용 (base.py:170-205) | ~~해결~~ | 불필요 |
| API 인증 없음 | P0 | **이미 구현됨** ✅ `@_require_api_key` 데코레이터 전 라우트 적용 (api/views.py:87,137), X-API-Key 헤더 검증 (16-76줄) | ~~해결~~ | 불필요 |
| 비밀번호 평문 저장 | P0 | **이미 수정됨** ✅ `werkzeug.security.check_password_hash()` 사용 (auth.py:220) | ~~해결~~ | 불필요 |
| 재고 이중커밋 | P0 | **RPC 레벨 멱등** ⚠️ `fn_commit_stock` RPC는 멱등하나, 호출부에서 `except Exception: pass`로 에러 무시 (packing/views.py:374-379, 449-454) | **P1** | except pass 제거 → 로깅 |
| 수식 평가기 eval 위험 | P1 | **제한적 eval 사용** ⚠️ `eval(expr, {"__builtins__": {}}, _SAFE_FUNCS)` — builtins 차단 + 화이트리스트 함수만 허용 (billing_engine.py:48). 블랙리스트+화이트리스트 이중 방어 적용됨 | **P2** | simpleeval 전환 권장이나 긴급하진 않음 |
| 역분개 미구현 | P0.5 | **확인: TODO 상태** ❌ `cancel_billing_event()` 함수 존재하나 내부 `pass`만 (billing_engine.py:390-394). 호출처도 없음 | **P1** | 음수 정정 트랜잭션 구현 필요 |
| Rate limiting 인메모리 | P1 | **확인: 인메모리** ⚠️ `_ip_login_attempts = defaultdict(list)` (auth.py:20-21). 재시작 시 초기화. 단, 계정 잠금은 DB 기반 (auth.py:113-134) | **P2** | DB 기반 전환 또는 유지 (계정잠금이 DB라 실질 방어됨) |
| 소프트삭제 캐스케이드 | P1 | 코드 확인 필요 (이번 검증 범위 외) | P1 유지 | 확인 후 판단 |

### AutoTool (ERP/WMS)

| AI 지적 | 등급 | 실제 코드 확인 결과 | 실제 등급 | 조치 |
|---------|------|---------------------|-----------|------|
| db_supabase.py God Object | P1 | **확인: 5,051줄 255메서드** — 사실 | P1 유지 | Mixin 분리 |
| 숨은 tenant 격리 누락 | — | **실제로 존재** 🔴 update/delete에서 biz_id 없이 id만으로 조작하는 함수 다수 발견 (db_supabase.py: 212, 329, 334, 562, 580, 873, 879, 943, 4500, 4514 등) | **P0** | biz_id 필터 추가 필수 |
| API 주문수집 롤백 불완전 | — | **확인** 🔴 다채널 순차 처리 시 실패한 채널만 롤백, 이전 채널은 커밋 유지 (orders_api.py:164-172). 또한 rollback이 hard delete 사용 (db_supabase.py:2566) | **P1** | 전체 채널 롤백 또는 트랜잭션 래핑 |
| 롤백 에러 로깅 누락 | — | **확인** ⚠️ 롤백 실패 시 response JSON에만 기록, `logger.error()` 없음 (orders_api.py:165-172) | **P2** | logger.error 추가 |
| 테스트 0건 | P0 | **확인: 0건** | P0 유지 | 핵심 10개 |

---

## 2. AI들이 틀린 것 (과대평가된 위험)

| 항목 | AI 판정 | 실제 | 이유 |
|------|---------|------|------|
| PackFlow 멀티테넌트 격리 | P0 위험 | ✅ 해결됨 | 보안 리뷰(03-18) 이후 코드 수정 완료. AI는 설계서의 과거 이슈를 현재로 오인 |
| PackFlow API 인증 | P0 위험 | ✅ 구현됨 | `@_require_api_key` + api_keys 테이블 + 해시 비교 모두 구현됨 |
| PackFlow 비밀번호 | P0 위험 | ✅ 수정됨 | werkzeug 해싱 적용 완료 |
| 수식 eval 보안 | P1 위험 | P2 주의 | builtins 차단 + 화이트리스트 이중 방어로 실질적 공격 벡터 제한적 |

**교훈**: 보안 리뷰 문서(03-18)에 "미수정"으로 기록된 이슈 중 상당수가 이후 커밋에서 이미 수정됨. AI는 설계서 시점의 상태를 현재로 판단.

---

## 3. AI들이 맞은 것 (실제 위험)

| 항목 | AI 판정 | 실제 | 영향 |
|------|---------|------|------|
| **AutoTool tenant 격리** | GPT만 경고 | 🔴 실제 존재 | 실운영 중이라 더 위험. 10개+ 함수에서 biz_id 미검증 |
| **역분개 미구현** | GPT: P0.5 | ❌ TODO pass | 3PL 정산 조정 불가 → 엑셀 회귀 |
| **재고 커밋 에러 무시** | 양쪽 지적 | ⚠️ except pass | 에러 발생해도 무시됨 |
| **API 롤백 불완전** | GPT만 지적 | 🔴 확인됨 | 다채널 중간 실패 시 부분 데이터 잔류 |
| **테스트 부재** | 양쪽 합의 | 확인 | AutoTool 0건, PackFlow 3건 |

---

## 4. 실제 해야 할 것 — 우선순위 재정렬

### Phase 1: 즉시 (1~2주) — 실제 P0

| # | 작업 | 시스템 | 공수 | 상세 |
|---|------|--------|------|------|
| 1 | **AutoTool tenant 격리 수정** | AutoTool | 8h | db_supabase.py 10개+ update/delete 함수에 biz_id 필터 추가. `delete_stock_ledger_all`, `delete_revenue_all` 등 전수조사 |
| 2 | **역분개 최소 구현** | PackFlow | 4h | `cancel_billing_event()` — 음수 정정 트랜잭션 Insert. Append-only |
| 3 | **재고 커밋 except pass 제거** | PackFlow | 2h | packing/views.py 3곳의 bare except → 로깅 + 사용자 알림 |
| **소계** | | | **14h** | |

### Phase 2: 긴급 (3~4주) — P1

| # | 작업 | 시스템 | 공수 | 상세 |
|---|------|--------|------|------|
| 4 | **API 롤백 로직 개선** | AutoTool | 4h | 다채널 실패 시 이전 채널도 롤백 + hard delete → soft delete 전환 |
| 5 | **핵심 테스트 10개** | 양쪽 | 10h | GPT 제안 채택: PackFlow 5개 + AutoTool 5개 |
| 6 | **GitHub Actions CI** | 양쪽 | 2h | pytest + ruff |
| 7 | **고객포털 완성** | PackFlow | 12h | 조회+과금내역+대시보드 (Gemini: 세일즈 포인트) |
| 8 | **롤백 에러 로깅 추가** | AutoTool | 1h | orders_api.py에 logger.error 추가 |
| **소계** | | | **29h** | |

### Phase 3: 중요 (5~8주) — P2

| # | 작업 | 시스템 | 공수 | 상세 |
|---|------|--------|------|------|
| 9 | **db_supabase.py Mixin 분리** | AutoTool | 15h | 5도메인 (orders, stock, settlement, marketplace, accounting) |
| 10 | **수식 평가기 simpleeval 전환** | PackFlow | 3h | 현재도 안전하나 eval 제거가 이상적 |
| 11 | **Rate limit DB 전환** | PackFlow | 3h | 계정잠금은 DB지만 IP 제한도 DB로 |
| 12 | **tenacity 라이브러리 도입** | AutoTool | 3h | 커스텀 재시도 → 표준 데코레이터 |
| 13 | **billing 서비스 분할** | PackFlow | 6h | rate_matcher/formula_eval/invoice_builder/reversal |
| **소계** | | | **30h** | |

### Phase 4: 백로그 (베타 후)

| # | 작업 | 근거 |
|---|------|------|
| 14 | 듀얼모드 웨이브 분할 | Gemini P2 — 베타에선 보수적 유지 (GPT 동의) |
| 15 | 중량계 API 연동 | Gemini |
| 16 | Pydantic 모델 도입 | Gemini |
| 17 | Sentry 에러 모니터링 | Claude 보충 |
| 18 | staging/prod 환경 분리 | Claude 보충 |

---

## 5. 시간 배분 최종

| | GPT 제안 | Gemini 제안 | 검증 후 최종 |
|--|---------|------------|-------------|
| AutoTool | 30% | 10% | **25%** — tenant 격리 P0 발견으로 상향 |
| PackFlow | 70% | 90% | **75%** |

**근거**: AutoTool에서 실제 P0 tenant 격리 이슈가 발견되었으므로 Gemini의 10%는 위험. 하지만 AutoTool은 기능 추가가 아닌 보안 수정이므로 25%면 충분.

---

## 6. 보안 리뷰 문서 업데이트 필요

`3pl/docs/security_review_20260318.md`의 판정표가 현재 코드와 불일치:

| 이슈 | 문서 상태 | 실제 상태 | 조치 |
|------|-----------|-----------|------|
| 멀티테넌트 격리 | ❌ 미수정 | ✅ 수정됨 | 문서 업데이트 |
| API 인증 | ❌ 미수정 | ✅ 구현됨 | 문서 업데이트 |
| 비밀번호 평문 | ✅ 수정 | ✅ 수정됨 | 일치 |
| 브루트포스 | ⚠️ 부분 | ⚠️ 부분 (IP=인메모리, 계정=DB) | 일치 |

→ 보안 리뷰 문서를 최신 코드 반영으로 갱신해야 AI 재검토 시 오판 방지

---

## 7. 총 공수 요약

| Phase | 기간 | 공수 | 핵심 |
|-------|------|------|------|
| Phase 1 | 2주 | 14h | AutoTool P0 보안 + PackFlow 역분개 |
| Phase 2 | 2주 | 29h | 테스트 + 고객포털 + 롤백 개선 |
| Phase 3 | 4주 | 30h | 구조 개선 + 안정화 |
| **합계** | **8주** | **73h** | |

기존 AI 예상(85~106h)보다 **20~30% 감소** — 이미 수정된 P0 3건 제외 효과

---

## 8. 최종 한줄

> **AI들이 가장 위험하다고 한 PackFlow P0 3건은 이미 수정되어 있었다.**
> **대신 AI들이 놓쳤거나 약하게 본 AutoTool tenant 격리가 실제 P0다.**
> **Phase 1: AutoTool biz_id 필터 + PackFlow 역분개 = 14시간이 진짜 임계점.**
