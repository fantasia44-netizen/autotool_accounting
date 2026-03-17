# PackFlow 보안 검토서 — 실제 코드 기반 검증

**작성일**: 2026-03-18
**검토 대상**: GPT/Gemini 보안 지적 4건 + 실제 코드 대조
**검증 범위**: base.py, auth.py, config.py, views.py, services 전체, repositories 전체

---

## 요약 판정표

| # | GPT/Gemini 지적 | 실제 코드 상태 | 판정 | 우선순위 |
|---|----------------|--------------|------|---------|
| 1 | 멀티테넌트 격리 (RLS off) | **부분적으로 유효 — _update/_delete before스냅샷에 실제 누락 확인** | 🔴 실제 위험 | P0 |
| 2 | 파일 스토리지 악용 | **MIME는 header만 검증, 크기 100MB 제한 있음, Rate Limit 없음** | 🟡 중간 위험 | P2 |
| 3 | 현장 API CSRF/인증 | **모든 현장 API에 @login_required + @_require_packing 적용 확인** | 🟢 안전 | — |
| 4 | 소프트 삭제 고아 데이터 | **캐스케이드 로직 없음, P&L에 삭제 고객 과금 포함됨** | 🟡 중간 위험 | P1 |
| + | 비밀번호 평문 저장 | **CRITICAL — bcrypt 미적용, 평문 비교** | 🔴 최우선 | P0 |
| + | 로그인 브루트포스 | **Rate limit 없음, 잠금 없음** | 🔴 긴급 | P0 |
| + | 외부 API 인증 없음 | **/api/v1/* 완전 공개 (TODO 상태)** | 🔴 긴급 | P0 |
| + | 재고 2-Phase 이중커밋 | **commit_stock() 비멱등, 동시 호출 시 이중 차감** | 🟡 중간 위험 | P1 |

---

## 🔴 1. 멀티테넌트 격리 — 실제 코드 검증 결과

### GPT/Gemini 지적
> RLS off 상태에서 앱 레벨 필터만 사용 → 개발자 실수 시 테넌트 침범

### 실제 코드 확인 결과

#### ✅ 안전한 부분
- `_query()`: `_apply_tenant_filter()` 자동 적용 (base.py:114)
- `_insert()`: `payload['operator_id'] = self.operator_id` 자동 주입
- `_update()`: UPDATE 쿼리 자체에 `_apply_tenant_filter()` 적용 (base.py:176-178)
- `_delete()`: soft/hard 모두 `_apply_tenant_filter()` 적용 (base.py:221, 232)
- `_restore()`: `_apply_tenant_filter()` 적용 (base.py:246-247)

#### 🔴 실제 취약점 발견 (3건)

**취약점 A: _update() before 스냅샷 — operator_id 필터 누락**
```python
# base.py:170 — 감사로그용 before 스냅샷
q = self.client.table(table).select('*').eq('id', record_id)  # ← operator_id 없음!
res = q.execute()
before = res.data[0] if res.data else None
```
- **위험**: ID만으로 다른 테넌트 데이터를 읽어서 audit_logs에 기록
- **공격 시나리오**: 테넌트A가 테넌트B의 record_id로 _update 호출 → UPDATE는 실패(tenant필터)하지만 before 스냅샷에 테넌트B 데이터 노출
- **심각도**: CRITICAL (정보 유출)

**취약점 B: _delete() before 스냅샷 — 동일 문제**
```python
# base.py:201 — 삭제 전 스냅샷
q = self.client.table(table).select('*').eq('id', record_id)  # ← operator_id 없음!
```
- _update()와 동일한 문제

**취약점 C: _upsert() — UPDATE 페이즈에 tenant 필터 불가**
```python
# base.py:255-260
res = self.client.table(table).upsert(payload, on_conflict=on_conflict).execute()
```
- Supabase upsert()는 `.eq()` 체이닝 미지원
- on_conflict 키가 겹치면 다른 테넌트 레코드를 덮어쓸 가능성
- **실제 사용처**: `inventory_repo.upsert_stock()` → `on_conflict='sku_id,location_id,lot_number'`
  - operator_id가 on_conflict에 포함되지 않으므로, 동일 sku_id+location_id 조합 시 충돌 가능
  - **단, 현재 sku_id 자체가 tenant별 고유이므로 실질적 위험은 낮음**

### 수정 방안
```python
# _update() before 스냅샷 수정
q = self.client.table(table).select('*').eq('id', record_id)
if table not in self.NO_TENANT_TABLES:
    q = self._apply_tenant_filter(q)  # ← 추가
res = q.execute()

# _delete() before 스냅샷 동일 수정

# _upsert() on_conflict에 operator_id 포함
on_conflict='operator_id,sku_id,location_id,lot_number'
```

### RLS 활성화 판단
- **현 단계(프리런칭)**: 앱 레벨 필터 수정으로 충분
- **상용화 시(5월)**: RLS 활성화 필수 → operator_id 기반 정책
- **참고**: service_role key는 RLS를 우회하므로, anon key 사용 전환 필요

---

## 🟡 2. 파일 스토리지 — 실제 코드 검증 결과

### GPT/Gemini 지적
> MIME 위장, 용량 폭탄, 랜섬웨어 업로드 위험

### 실제 코드 확인 결과

#### ✅ 안전한 부분
- **파일 크기 제한**: 100MB 서버 사이드 검증 (views.py:327-330)
- **MIME 타입 검증**: 4종 허용 (views.py:312-314)
- **경로 조작 방지**: 서버 생성 경로 사용 — `packing/{날짜}/{user_id}_{barcode}_{timestamp}.webm`
- **권한 검증**: `job.user_id == current_user.id` 소유권 확인 (views.py:323)
- **서명 URL**: 1시간 만료 (packing_repo.py:67)

#### 🟡 보완 필요 (3건)

**보완 A: MIME 검증이 Content-Type 헤더만 확인**
```python
allowed_video = ('video/webm', 'video/mp4', 'video/ogg', 'video/quicktime')
if video_file.content_type not in allowed_video:  # ← 헤더만 확인
```
- 바이너리 매직 바이트(file signature) 미검증
- 공격자가 Content-Type 헤더를 조작하면 임의 파일 업로드 가능

**보완 B: 업로드 Rate Limit 없음**
- 테넌트/사용자별 일일 업로드 횟수 제한 없음
- DoS 공격 시 스토리지 비용 폭탄 가능

**보완 C: barcode 경로 주입 가능성**
```python
path = f".../{current_user.id}_{job.get('scanned_barcode', '')}_{ts}.webm"
```
- `scanned_barcode`에 `/` 또는 `..` 포함 시 디렉토리 조작 가능
- **수정**: barcode에서 `/\..` 제거 필요

### 수정 방안
```python
# 매직 바이트 검증 추가
MAGIC_BYTES = {
    b'\x1a\x45\xdf\xa3': 'video/webm',
    b'\x00\x00\x00\x18': 'video/mp4',  # ftyp
    b'\x00\x00\x00\x1c': 'video/mp4',
}
header = video_bytes[:4]
if header not in MAGIC_BYTES:
    return jsonify({'ok': False, 'error': '잘못된 영상 파일'})

# barcode 경로 안전화
import re
safe_barcode = re.sub(r'[^a-zA-Z0-9_-]', '', job.get('scanned_barcode', ''))
```

---

## 🟢 3. 현장 API CSRF/인증 — 실제 코드 검증 결과

### GPT/Gemini 지적
> 모바일 현장 API에 CSRF 토큰이 엄격히 검증되는지, 인증이 느슨하지 않은지

### 실제 코드 확인 결과: **모두 안전**

#### ✅ 전체 현장 API 인증 상태

| 엔드포인트 | @login_required | @_require_packing | CSRF |
|-----------|:-:|:-:|:-:|
| `api/field/inbound` | ✅ | ✅ | ✅ (packing_bp는 CSRF 면제 아님) |
| `api/field/transfer` | ✅ | ✅ | ✅ |
| `api/field/stock-at-location` | ✅ | ✅ | ✅ |
| `api/field/stockcheck` | ✅ | ✅ | ✅ |
| `api/field/shipping-scan` | ✅ | ✅ | ✅ |
| `api/field/sku-lookup` | ✅ | ✅ | ✅ |

- **CSRF**: packing_bp는 csrf.exempt 대상이 **아님** (api_bp만 면제)
- **CSRF 토큰 전달**: base.html의 `<meta name="csrf-token">` + Ajax 자동 주입
- **추가 보호**: 촬영모드에서 `job.user_id == current_user.id` 소유권 확인

#### ⚠️ 단, 외부 API(/api/v1)는 완전 공개 상태
```python
# app.py:134
app.csrf.exempt(api_bp)  # CSRF 면제
```
```python
# api/views.py — 인증 없음
@api_bp.route('/orders', methods=['POST'])
def create_order():
    # TODO: API key 인증 + 주문 생성
    return jsonify({'status': 'received'}), 201
```
- **판정**: 현장 API는 안전, 외부 API는 TODO 상태로 배포 전 반드시 구현 필요

---

## 🟡 4. 소프트 삭제 고아 데이터 — 실제 코드 검증 결과

### GPT/Gemini 지적
> 부모 삭제 시 자식 미처리 → 정산 오류, 통계 왜곡

### 실제 코드 확인 결과: **실제 문제 확인**

#### 🔴 확인된 문제 (3건)

**문제 A: P&L 계산에 삭제된 고객 과금 포함**
```python
# finance_service.py:45-49
all_billing = billing_repo._query(
    billing_repo.LOG_TABLE,
    filters=[('year_month', 'eq', year_month)],
    limit=5000
)
```
- `client_billing_logs`의 `is_deleted` 필터는 _query()에서 자동 적용됨 ✅
- **하지만** 삭제된 client에 대한 billing_log가 is_deleted=false로 남아있으면 매출에 포함됨
- 실제 시나리오: 고객사 해지 → 고객사만 삭제 → 해당 고객 과금 이력은 그대로 → P&L에 유령 매출

**문제 B: 캐스케이드 삭제 로직 부재**
- 고객사(clients) 삭제 시 연쇄 처리되는 항목: **없음**
- SKU, 주문, 출고, 과금로그, 청구서 모두 독립적으로 살아있음
- 현재 코드에 cascade 관련 함수/로직 전무

**문제 C: _restore()에 참조 무결성 검증 없음**
```python
# base.py:237-253
def _restore(self, table, record_id):
    # 부모 테이블 존재 확인 없이 바로 복원
    q = self.client.table(table).update({
        'is_deleted': False, 'deleted_at': None, 'deleted_by': None
    }).eq('id', record_id)
```
- 삭제된 고객의 SKU를 복원 → 고객은 삭제 상태인데 SKU만 활성화

#### ✅ 안전한 부분
- `_query()` 자체는 SOFT_DELETE_TABLES에 대해 `is_deleted` 자동 필터 적용
- 일상적인 목록 조회에서는 삭제된 레코드가 표시되지 않음

### 수정 방안
```python
# 1. P&L 계산 시 활성 고객만 필터
active_clients = set(c['id'] for c in client_repo.list_clients())
revenue = sum(r['amount'] for r in all_billing if r.get('client_id') in active_clients)

# 2. 고객사 삭제 시 cascade 처리
def soft_delete_client_cascade(client_id):
    repo._delete('clients', client_id)
    for sku in inv_repo.list_skus(client_id=client_id):
        repo._delete('skus', sku['id'])
    # orders, shipments 등은 보존 (이력 목적) but 과금 중단

# 3. _restore() 시 부모 존재 확인
def _restore(self, table, record_id):
    record = self._get_record(table, record_id)
    if record.get('client_id'):
        client = self._query('clients', filters=[('id','eq',record['client_id'])])
        if not client:
            raise ValueError('부모 고객사가 삭제된 상태입니다')
```

---

## 🔴 5. 비밀번호 평문 저장 (GPT/Gemini 미언급 — Claude 추가 발견)

### 코드 증거
```python
# auth.py:51-52 (데모 모드)
if not demo_user or demo_user['password_hash'] != password:

# auth.py:70-71 (실서비스 모드)
# TODO: bcrypt 비밀번호 검증 추가
if row.get('password_hash') != password:  # ← 평문 비교!
```

### 판정: **CRITICAL — 즉시 수정 필수**
- DB 유출 시 모든 사용자 비밀번호 노출
- `password_hash` 컬럼명만 hash이지 실제 해싱 안 됨
- 하드코딩된 데모 계정: `admin/test1234`, `client1/test1234`, `packer1/test1234`

### 수정 방안
```python
from werkzeug.security import generate_password_hash, check_password_hash

# 회원가입 시
hashed = generate_password_hash(password, method='pbkdf2:sha256')

# 로그인 시
if not check_password_hash(row['password_hash'], password):
    flash('비밀번호 불일치')
```

---

## 🔴 6. 로그인 브루트포스 방어 없음

### 코드 증거
```python
# auth.py — 로그인 처리
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        # Rate limit 없음, 실패 횟수 추적 없음, 잠금 없음
```

### 수정 방안
```python
from flask_limiter import Limiter
limiter = Limiter(key_func=get_remote_address)

@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute")  # IP당 분당 5회
def login():
    ...
```

---

## 🟡 7. 재고 2-Phase Commit 이중 커밋 위험

### 코드 증거
```python
# inventory_service.py:91-132
def commit_stock(inv_repo, order_id):
    reservations = inv_repo.list_reservations(order_id, status='reserved')
    # 1) 상태 확인 없이 바로 커밋
    # 2) 트랜잭션 래핑 없음
    # 3) 멱등성 보장 없음
    for res in reservations:
        inv_repo.adjust_stock(...)
        inv_repo.update_reservation_status(res['id'], 'committed', now)
```

```python
# packing/views.py — 두 곳에서 호출
# api_complete_job (line 376) + api_complete_job_no_video (line 451)
try:
    commit_stock(inv_repo, order_id)
except Exception:
    pass  # 실패 무시
```

### 위험 시나리오
1. 완료 버튼 더블클릭 → commit_stock 2회 호출 → 재고 이중 차감
2. 네트워크 타임아웃 → 클라이언트 재시도 → 동일

### 수정 방안
```python
def commit_stock(inv_repo, order_id):
    reservations = inv_repo.list_reservations(order_id, status='reserved')
    if not reservations:
        return {'ok': True, 'message': '이미 처리됨'}  # 멱등성
    # 주문 상태 확인
    order = order_repo.get_order(order_id)
    if order.get('status') in ('cancelled', 'hold'):
        return {'ok': False, 'error': '취소/보류된 주문'}
```

---

## 🟡 8. 현장 API 중복 요청 방지 (dedupe_key 미적용)

### 코드 증거
- **과금 서비스**: dedupe_key 사용 중 ✅ (`client_billing_service.py`)
- **현장모드 API**: dedupe_key **미사용** ❌

| API | dedupe 방지 | 위험 |
|-----|:-:|------|
| api/field/inbound | ❌ | 새로고침 → 입고 이중 반영 |
| api/field/transfer | ❌ | 네트워크 재시도 → 이중 이동 |
| api/field/stockcheck | ❌ | (조정이라 위험 낮음) |
| api/field/shipping-scan | ❌ | 이미 출고 체크 있어서 낮음 |

### 수정 방안
```python
# 현장 API에 클라이언트 측 dedupe
import hashlib, time
dedupe = hashlib.md5(f"{barcode}:{location_id}:{int(time.time()//60)}".encode()).hexdigest()
# 1분 내 동일 요청 무시
```

---

## 우선순위별 실행 계획

### P0 — 즉시 (상용화 전 필수)
| # | 항목 | 예상 작업량 | 파일 |
|---|------|-----------|------|
| 1 | 비밀번호 bcrypt 해싱 | 30분 | auth.py |
| 2 | _update/_delete before 스냅샷 tenant 필터 | 15분 | base.py:170, 201 |
| 3 | 로그인 Rate Limit (flask-limiter) | 1시간 | auth.py, app.py |
| 4 | 외부 API 인증 구현 또는 비활성화 | 1시간 | api/views.py |

### P1 — 단기 (2주 내)
| # | 항목 | 예상 작업량 | 파일 |
|---|------|-----------|------|
| 5 | commit_stock 멱등성 + 상태 검증 | 2시간 | inventory_service.py |
| 6 | 고객사 삭제 캐스케이드 로직 | 3시간 | 신규 서비스 |
| 7 | P&L 삭제 고객 필터링 | 30분 | finance_service.py |
| 8 | _restore() 참조 무결성 검증 | 1시간 | base.py, admin_views.py |

### P2 — 중기 (1개월 내)
| # | 항목 | 예상 작업량 | 파일 |
|---|------|-----------|------|
| 9 | 영상 매직 바이트 검증 | 1시간 | packing/views.py |
| 10 | 업로드 Rate Limit (테넌트별) | 2시간 | packing/views.py |
| 11 | 현장 API dedupe_key | 2시간 | packing/views.py |
| 12 | barcode 경로 문자 안전화 | 30분 | packing/views.py |
| 13 | 세션 쿠키 SameSite=Strict | 5분 | config.py |

### P3 — 상용화 전 (2개월 내)
| # | 항목 | 예상 작업량 | 파일 |
|---|------|-----------|------|
| 14 | Supabase RLS 정책 활성화 | 1일 | DB 정책 |
| 15 | _upsert on_conflict에 operator_id 포함 | 1시간 | base.py, inventory_repo.py |
| 16 | 보안 이벤트 감사로그 (로그인실패, 권한거부) | 3시간 | auth.py, base.py |
| 17 | 관리자 2FA | 1일 | auth.py |
| 18 | 보안 헤더 (CSP, X-Frame-Options 등) | 1시간 | app.py |

---

## GPT/Gemini 지적 vs 실제 코드 최종 대조

| GPT/Gemini 주장 | 실제 확인 | 판정 |
|----------------|----------|------|
| "RLS off가 치명적" | update/delete before스냅샷에 실제 누락 있음. 단 _query/_update/_delete 본 쿼리는 필터 적용됨 | **부분 타당** — 스냅샷 수정으로 해결 가능 |
| "바이너리 헤더 검증 필요" | Content-Type 헤더만 검증, 매직 바이트 미확인 | **타당** |
| "현장 API CSRF 우회 위험" | 모든 현장 API에 @login_required + @_require_packing + CSRF 적용 확인 | **과대평가** — 실제로는 안전 |
| "소프트삭제 고아 데이터" | P&L에 삭제 고객 과금 포함 확인, 캐스케이드 없음 | **타당** |
| "앱 단 필터를 믿지 말라" | 필터 자체는 일관되게 적용되나, before 스냅샷 예외 존재 | **부분 타당** |
| "10GB 파일 업로드 폭탄" | 100MB 서버 제한 있음 | **과대평가** — 이미 제한됨 |

### Claude 추가 발견 (GPT/Gemini 미언급)
1. **비밀번호 평문 저장** — 가장 심각한 보안 결함
2. **로그인 브루트포스 방어 없음**
3. **외부 API 인증 미구현 (공개 상태)**
4. **commit_stock 이중 커밋 가능성**
5. **현장 API dedupe_key 미적용**

---

*이 문서는 실제 코드를 기반으로 검증한 보안 검토 결과이며, 우선순위별 수정 계획을 포함합니다.*
*구현은 별도 세션에서 진행합니다.*
