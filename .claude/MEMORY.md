# AutoTool Accounting / 3PL PackFlow — 프로젝트 메모리

> 3대 PC(회사/노트북/집) 모두 git pull로 동기화.
> 코드 수정 전 반드시 이 파일을 읽고 DB 테이블 매핑을 확인할 것.

## 레포 구조
- **autotool** (Private): 메인 통합시스템 (Flask + Supabase)
- **autotool_accounting** (Public): 회계 + 3PL PackFlow
  - `3pl/` 폴더: PackFlow SaaS (별도 Flask 앱)
  - 루트: 회계 관련 공유 코드/문서

## ⚠️ 치명적 교훈: DB 테이블명 — 절대 추측하지 말 것 (2026-03-25)

### cookdaddy Supabase (3PL용 DB)에는 비슷한 이름의 테이블이 공존한다:

| 3PL 코드가 사용 | AutoTool 전용 (사용 금지) | 차이점 |
|---|---|---|
| `users` (7rows, 14cols, **operator_id 있음**) | `app_users` (1row, 13cols, operator_id 없음) | 3PL은 멀티테넌트(operator_id) 필수 |
| `orders` (10rows, 23cols) | `api_orders` (0rows, 22cols) | 3PL PackFlow 주문 vs AutoTool API 주문 |

### 3PL 코드(`3pl/`)에서의 올바른 테이블명:
- **`users`** — auth.py, app.py user_loader, user_repo.py, admin_views.py
- **`orders`** — order_repo.py, base.py (SOFT_DELETE, _PARENT_REFS)
- `app_users`, `api_orders`는 AutoTool 메인 시스템 전용 → **3PL 코드에서 사용하면 에러남**

### 사고 경위:
1. 노트북에서 PGRST205 에러 → `users` 테이블을 `app_users`로 변경 시도
2. 메인PC에서 `orders`도 `api_orders`로 일괄 변경
3. 실제로는 DB에 `users`/`orders` 테이블이 따로 존재 → 원복 필요했음
4. `app_users`로 바꾸면 `operator_id does not exist` 에러 발생 (컬럼 구조 다름)

### 규칙:
- **테이블명 변경 전 반드시 Supabase 대시보드에서 실제 테이블 목록 확인**
- 비슷한 이름이라고 같은 테이블이 아님 (용도/컬럼이 다름)
- 에러가 나면 코드를 바꾸기 전에 DB 스키마부터 확인

## 환경 설정
- **메인 DB** (AutoTool): `SUPABASE_URL` / `SUPABASE_KEY` (autotool/.env)
- **3PL DB** (cookdaddy): `COOKDADDY_SUPABASE_URL` / `COOKDADDY_SUPABASE_KEY` (autotool/.env)
- 3PL 레포 자체에는 `.env` 없음 → autotool/.env에서 COOKDADDY_ 접두어로 관리
- 3PL 단독 실행 시 별도 `.env` 필요 (SUPABASE_URL/KEY = cookdaddy 값)

## 3PL 기술 스택
- Flask + Supabase, Multi-tenant (operator_id 기반)
- blueprints: api, client, operator, packing
- repositories: 10개+ (base.py에 SOFT_DELETE/PARENT_REFS 매핑)
- services: 15개+ (billing_engine, fulfillment_mode, kpi 등)
- 듀얼모드 풀필먼트 (일반/속도), 과금엔진 v2.0, 재고실사
