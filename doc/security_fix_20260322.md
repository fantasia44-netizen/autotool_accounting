# 보안 개선 작업 보고서 (2026-03-22)

## 개요
GPT/Gemini AI 리뷰에서 지적된 P0/P1 보안 이슈를 코드 레벨에서 수정하고,
로컬 시뮬레이션 + 실제 DB 연결 테스트로 검증 완료.

---

## 1. AutoTool — db_supabase.py 멀티테넌트 격리

### 문제
- 42개 update/delete 함수가 `id`만으로 레코드 조작 → 다른 테넌트 데이터 수정 가능
- 1개 함수에서 하드 삭제(`.delete()`) 사용 → 데이터 영구 손실 위험

### 수정 내용
- `_with_biz(query, biz_id)` 헬퍼 메서드 추가
  - biz_id가 주어지면 `.eq("biz_id", biz_id)` 자동 체이닝
  - biz_id=None(기본값)이면 기존 동작 유지 → **하위호환 보장**
- 42개 함수 모두 `biz_id=None` 파라미터 추가
- `rollback_import_run_full`의 하드 삭제 → 소프트 삭제 전환

### 수정 대상 테이블 (28개)
stock_ledger, daily_revenue, daily_closing, business_partners,
manual_trades, purchase_orders, option_master, app_users, audit_logs,
promotions, coupons, expenses, employees, payroll_monthly,
salary_components, bank_accounts, bank_transactions, tax_invoices,
payment_matches, platform_settlements, journal_entries, api_sync_log,
work_logs, api_orders, packing_jobs, product_costs, channel_costs,
card_transactions

### 테스트 결과 (실행됨)
```
[시뮬레이션 테스트] _test_biz_id_filter.py
  1. _with_biz 헬퍼: PASS
  2. 하위호환 (biz_id 미전달): 39/39 PASS
  3. biz_id 적용 (biz_id=42): 39/39 PASS
  4. 핵심 경로 시뮬레이션: PASS
  5. 하드삭제→소프트삭제 전환: PASS
  → 5/5 ALL PASS

[로컬 DB 연결 테스트]
  DB connect: True
  option_master: 2,622 rows 정상 조회
  biz_id param: 13/13 대표 함수 확인
```

### 커밋
- `a31d231` fix(security): db_supabase.py 멀티테넌트 biz_id 필터 추가 — 42개 함수

---

## 2. PackFlow — 테넌트 격리 + eval 제거

### 2-1. 테넌트 격리 (warehouse_repo.py)

**문제**: 3개 함수가 raw client 호출로 operator_id 필터 우회
- `update_location()`: `.eq('id', id)` 만으로 업데이트
- `list_all_locations()`: 전체 테이블 스캔 (테넌트 무관)
- `get_location()`: raw client 사용

**수정**:
- `update_location` → `self._update()` 베이스 메서드 사용 (자동 테넌트 격리)
- `list_all_locations` → 현재 테넌트 창고의 로케이션만 반환 (list_warehouses → zones → locations 체인)
- `get_location` → `self._query()` 사용으로 통일

**참고**: 나머지 27+ 함수는 base.py `_apply_tenant_filter()`로 이미 안전

### 2-2. eval() 제거 → AST 파서 (billing_engine.py)

**문제**: `eval(expr_str, {"__builtins__": {}}, _SAFE_FUNCS)` — 블랙리스트 방식 우회 가능

**수정**: AST 화이트리스트 파서로 완전 교체
- `ast.parse(expr, mode='eval')` → 재귀 노드 평가
- 허용 노드: `Constant(int/float)`, `BinOp(+−*/÷%**)`, `UnaryOp(−+)`, `Call(ceil/floor/min/max/abs/round)`
- 거듭제곱 지수 100 초과 차단 (DoS 방지)
- eval() 코드 완전 제거

### 2-3. 재고 이중커밋 멱등성
- RPC `fn_commit_stock`에서 이미 멱등성 보장 확인 (이미 committed면 무시)
- 추가 수정 불필요

### 테스트 결과 (실행됨)
```
[AST 파서 테스트] _test_ast_eval.py
  1. basic arithmetic: PASS
  2. parentheses: PASS
  3. unary operators: PASS
  4. safe functions: PASS
  5. complex billing formulas: PASS
  6. evaluate_formula with vars: PASS
  7. blocked 9/9 attacks: PASS
  8. power limit enforced: PASS
  → 8/8 ALL PASS

[역분개 테스트] _test_reversal.py
  → 5/5 ALL PASS

[로컬 검증]
  billing_engine import: OK (AST parser)
  Formula eval: 3/3 OK
  Attack blocked: 5/5
  update_location uses _update: OK
  list_all_locations tenant filter: OK
```

### 커밋
- `a55e821` fix(3pl/security): 테넌트 격리 + eval 제거 + AST 파서 도입

---

## 3. GPT/Gemini 리뷰 대비 해결 현황

| AI 지적 사항 | 상태 | 비고 |
|---|---|---|
| AutoTool God Object (db_supabase.py 5,051줄) | 인지됨 | 실운영 중이므로 신규코드부터 분리 원칙 |
| AutoTool biz_id 누락 42개 함수 | **수정 완료** | _with_biz 헬퍼 + 하위호환 |
| AutoTool 하드 삭제 | **수정 완료** | 소프트 삭제 전환 |
| PackFlow 테넌트 격리 누락 | **수정 완료** | warehouse_repo 3함수 |
| PackFlow eval() 보안 | **수정 완료** | AST 화이트리스트 교체 |
| PackFlow 재고 이중커밋 | **확인 완료** | RPC 레벨 멱등성 이미 보장 |
| PackFlow 과금 역분개 | **이전 구현 완료** | cancel_billing_event() |
| 테스트 부재 | **부분 해결** | 핵심 경로 시뮬레이션 테스트 3개 파일 추가 |
| API 인증 | 미착수 | API Key + HMAC 방식 예정 |
| RLS 활성화 | 미착수 | Supabase DB 레벨 설정 필요 |
