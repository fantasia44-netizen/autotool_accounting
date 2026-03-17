"""테스트용 요금표 단가 일괄 설정 스크립트."""
import os, sys
app_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(app_dir)
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(app_dir, '.env'))

from supabase import create_client
url = os.environ.get('SUPABASE_URL')
key = os.environ.get('SUPABASE_KEY')
db = create_client(url, key)

# 쿡대디(client_id=1)의 요금표 조회
rates = db.table('client_rates').select('*').eq('client_id', 1).execute().data
print(f'현재 요금표: {len(rates)}개')

# 테스트 단가 설정
PRICES = {
    '입고검수비': 5000,
    '상차비': 15000,
    '하차비': 15000,
    '출고작업비': 3000,
    '합포장추가비': 1000,
    '일반보관비': 50,      # 개/일
    '냉장보관비': 80,
    '냉동보관비': 120,
    '기본택배비': 3500,
    '사이즈추가비': 1000,
    '중량추가비': 500,     # kg당
    '박스': 800,
    '아이스팩': 300,
    '드라이아이스': 500,
    '완충재': 200,
    '테이프': 100,
    '반품수수료': 5000,
    '반품검수비': 2000,
    '라벨부착': 500,
    '키팅': 1500,
    '사진촬영': 3000,
}

updated = 0
for rate in rates:
    name = rate.get('fee_name', '')
    if name in PRICES:
        db.table('client_rates').update({'amount': PRICES[name]}).eq('id', rate['id']).execute()
        print(f'  {name}: {PRICES[name]:,}원')
        updated += 1

print(f'\n완료: {updated}개 항목 단가 설정')
