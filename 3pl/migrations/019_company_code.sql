-- ============================================================
-- 019: 멀티테넌트 SaaS 기반 — 회사코드(company_code)
-- ============================================================

-- 1. operators 테이블: 회사코드 추가
ALTER TABLE operators ADD COLUMN IF NOT EXISTS company_code TEXT;

-- 기존 운영사에 기본 코드 부여 (ID 기반)
UPDATE operators SET company_code = UPPER('OP' || LPAD(id::TEXT, 4, '0'))
WHERE company_code IS NULL;

-- UNIQUE 제약 추가
CREATE UNIQUE INDEX IF NOT EXISTS idx_operators_company_code
    ON operators(company_code) WHERE company_code IS NOT NULL;

COMMENT ON COLUMN operators.company_code IS '회사 고유코드 (로그인/가입 시 식별자, 예: BAEMAMA)';

-- 2. users 테이블: username UNIQUE 제약 제거 → (operator_id, username) UNIQUE로 변경
-- 다른 운영사에서 같은 username 사용 가능하도록
-- 기존 username UNIQUE 인덱스 삭제 (있으면)
DROP INDEX IF EXISTS users_username_key;
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key;

-- 운영사별 username 유일성 보장
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_operator_username
    ON users(operator_id, username);
