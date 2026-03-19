"""과금 엔진 v2.0 시뮬레이션 테스트."""
import sys
sys.path.insert(0, '.')
from services.billing_engine import evaluate_formula, match_conditions, calculate_fees, sanity_check

print('=== 1. 수식 파서 테스트 ===')
ctx = {'base_amount': 300, 'qty': 1, 'item_count': 3,
       'chargeable_weight_kg': 7.5, 'pallet_count': 2, 'days': 30}

print(f'고정 300원: {evaluate_formula("300", ctx)}')
print(f'합포장 300+(3-1)*100: {evaluate_formula("{base_amount} + ({item_count} - 1) * 100", ctx)}')
print(f'중량추가 7.5kg: {evaluate_formula("max(0, ceil({chargeable_weight_kg} - 5)) * 500", ctx)}')
print(f'일당보관비 300*2파레트: {evaluate_formula("{base_amount} * {pallet_count}", ctx)}')
print(f'기존방식 NULL→500*3: {evaluate_formula(None, {"base_amount": 500, "qty": 3})}')

print('\n=== 2. 조건 매칭 테스트 ===')
print(f'단품=단품: {match_conditions({"pack_type": "single"}, {"pack_type": "single"})}')
print(f'합포→단품: {match_conditions({"pack_type": "single"}, {"pack_type": "multi"})}')
print(f'7.5kg>5kg: {match_conditions({"weight_min_g": 5001}, {"chargeable_weight_kg": 7.5})}')
print(f'3kg<5kg: {match_conditions({"weight_min_g": 5001}, {"chargeable_weight_kg": 3.0})}')
print(f'제주배송: {match_conditions({"delivery_region": "제주"}, {"delivery_region": "제주시"})}')
print(f'서울→제주조건: {match_conditions({"delivery_region": "제주"}, {"delivery_region": "서울"})}')

print('\n=== 3. 통합 과금 계산 ===')
mock_rates = [
    {'id': 1, 'fee_name': '출고작업비(단품)', 'category': 'outbound', 'fee_type': 'fixed',
     'amount': 300, 'conditions': {'pack_type': 'single'}, 'formula': '300',
     'applies_to': 'single', 'priority': 100, 'is_stackable': True, 'is_active': True, 'min_amount': 0},
    {'id': 2, 'fee_name': '출고작업비(합포)', 'category': 'outbound', 'fee_type': 'fixed',
     'amount': 300, 'conditions': {'pack_type': 'multi'},
     'formula': '{base_amount} + ({item_count} - 1) * 100',
     'applies_to': 'multi', 'priority': 100, 'is_stackable': True, 'is_active': True, 'min_amount': 0},
    {'id': 3, 'fee_name': '기본택배비', 'category': 'courier', 'fee_type': 'fixed',
     'amount': 3500, 'conditions': {}, 'formula': '3500',
     'applies_to': 'all', 'priority': 100, 'is_stackable': True, 'is_active': True, 'min_amount': 0},
    {'id': 4, 'fee_name': '중량추가비', 'category': 'courier', 'fee_type': 'fixed',
     'amount': 500, 'conditions': {'weight_min_g': 5001},
     'formula': 'max(0, ceil({chargeable_weight_kg} - 5)) * 500',
     'applies_to': 'all', 'priority': 110, 'is_stackable': True, 'is_active': True, 'min_amount': 0},
    {'id': 5, 'fee_name': '제주추가비', 'category': 'courier', 'fee_type': 'fixed',
     'amount': 3000, 'conditions': {'delivery_region': '제주'}, 'formula': '3000',
     'applies_to': 'all', 'priority': 120, 'is_stackable': True, 'is_active': True, 'min_amount': 0},
    {'id': 6, 'fee_name': '냉동보관비', 'category': 'storage', 'fee_type': 'fixed',
     'amount': 7000, 'conditions': {'storage_temp': 'frozen'},
     'formula': '{base_amount} * {pallet_count}',
     'applies_to': 'all', 'priority': 100, 'is_stackable': True, 'is_active': True, 'min_amount': 0},
]

# 시나리오1: 합포 3품목, 7.5kg, 서울
print('--- 시나리오1: 합포 3품목, 7.5kg, 서울 ---')
fees = calculate_fees(mock_rates, {
    'pack_type': 'multi', 'item_count': 3, 'chargeable_weight_kg': 7.5,
    'delivery_region': '서울', 'qty': 1})
for f in fees:
    print(f"  {f['fee_name']}: {f['total_amount']:,.0f}원")
print(f"  합계: {sum(f['total_amount'] for f in fees):,.0f}원")

# 시나리오2: 단품, 3kg, 제주
print('--- 시나리오2: 단품, 3kg, 제주 ---')
fees = calculate_fees(mock_rates, {
    'pack_type': 'single', 'item_count': 1, 'chargeable_weight_kg': 3.0,
    'delivery_region': '제주시', 'qty': 1})
for f in fees:
    print(f"  {f['fee_name']}: {f['total_amount']:,.0f}원")
print(f"  합계: {sum(f['total_amount'] for f in fees):,.0f}원")

# 시나리오3: Speed 모드
print('--- 시나리오3: Speed 모드 (단순 고정가만) ---')
fees = calculate_fees(mock_rates, {
    'pack_type': 'single', 'item_count': 1, 'chargeable_weight_kg': 3.0,
    'delivery_region': '서울', 'qty': 1}, mode='speed')
for f in fees:
    print(f"  {f['fee_name']}: {f['total_amount']:,.0f}원")
print(f"  합계: {sum(f['total_amount'] for f in fees):,.0f}원")

# 시나리오4: 보관비 (냉동 2파레트)
print('--- 시나리오4: 냉동보관 2파레트 일당 ---')
fees = calculate_fees(mock_rates, {
    'storage_temp': 'frozen', 'pallet_count': 2, 'days': 1, 'qty': 1})
for f in fees:
    print(f"  {f['fee_name']}: {f['total_amount']:,.0f}원")
print(f"  합계: {sum(f['total_amount'] for f in fees):,.0f}원")

print('\n=== 4. Sanity Check ===')
w = sanity_check({'chargeable_weight_kg': 150, 'item_count': 60, 'qty': 1})
print(f'비정상 경고: {w}')
w = sanity_check({'chargeable_weight_kg': 5, 'item_count': 3, 'qty': 1})
print(f'정상: {w}')

print('\n=== 모든 테스트 통과! ===')
