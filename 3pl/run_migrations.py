"""Supabase 마이그레이션 실행기.

사용법:
  py run_migrations.py                  # 전체 실행
  py run_migrations.py 008 009          # 특정 번호만 실행
"""
import sys
import os
import glob

DB_URL = os.environ.get("DATABASE_URL", "")

if not DB_URL:
    print("=" * 50)
    print("DATABASE_URL 환경변수가 필요합니다.")
    print()
    print("Supabase > Project Settings > Database")
    print("> Connection string > URI 복사")
    print()
    print('set DATABASE_URL=postgresql://postgres.xxxxx:비밀번호@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres')
    print()
    print("또는 직접 입력:")
    DB_URL = input("DB URL: ").strip()
    if not DB_URL:
        sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("psycopg2 미설치 → py -m pip install psycopg2-binary")
    sys.exit(1)

migration_dir = os.path.join(os.path.dirname(__file__), "migrations")
files = sorted(glob.glob(os.path.join(migration_dir, "*.sql")))

# 특정 번호 필터
if len(sys.argv) > 1:
    targets = sys.argv[1:]
    files = [f for f in files if any(os.path.basename(f).startswith(t) for t in targets)]

if not files:
    print("실행할 마이그레이션 파일이 없습니다.")
    sys.exit(0)

print(f"\n실행할 마이그레이션 {len(files)}개:")
for f in files:
    print(f"  {os.path.basename(f)}")

confirm = input("\n실행하시겠습니까? (y/N): ").strip().lower()
if confirm != "y":
    print("취소됨")
    sys.exit(0)

conn = psycopg2.connect(DB_URL)
conn.autocommit = False

try:
    cur = conn.cursor()
    for filepath in files:
        name = os.path.basename(filepath)
        print(f"\n▶ {name} 실행중...")
        with open(filepath, "r", encoding="utf-8") as f:
            sql = f.read()
        try:
            cur.execute(sql)
            conn.commit()
            print(f"  ✓ {name} 완료")
        except Exception as e:
            conn.rollback()
            print(f"  ✗ {name} 실패: {e}")
            retry = input("  계속 진행? (y/N): ").strip().lower()
            if retry != "y":
                break
    cur.close()
finally:
    conn.close()

print("\n완료!")
