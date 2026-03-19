"""과금 엔진 v2.0 — 실제 시나리오 테스트 (출고작업 A/B)."""
import sys
sys.path.insert(0, '.')
from services.billing_engine import calculate_fees

# 고객사 요금표 세팅 (실제 DB에 넣을 요금)
client_rates = [
    # ── 출고 작업비 ──
    {'id': 1, 'fee_name': '기본작업비', 'category': 'outbound', 'amount': 500,
     'conditions': {'pack_type': 'single'}, 'formula': '500',
     'applies_to': 'single', 'priority': 100, 'is_stackable': True, 'is_active': True, 'min_amount': 0},
    {'id': 2, 'fee_name': '기본작업비(중형)', 'category': 'outbound', 'amount': 800,
     'conditions': {'pack_type': 'single', 'weight_min_g': 5001}, 'formula': '800',
     'applies_to': 'single', 'priority': 90, 'is_stackable': False, 'is_active': True, 'min_amount': 0},
    {'id': 3, 'fee_name': '동종포장추가비', 'category': 'outbound', 'amount': 100,
     'conditions': {}, 'formula': 'max(0, {same_item_count} - 1) * {base_amount}',
     'applies_to': 'all', 'priority': 110, 'is_stackable': True, 'is_active': True, 'min_amount': 0},
    {'id': 4, 'fee_name': '합포장추가비', 'category': 'outbound', 'amount': 150,
     'conditions': {}, 'formula': 'max(0, {multi_item_count} - 1) * {base_amount}',
     'applies_to': 'all', 'priority': 120, 'is_stackable': True, 'is_active': True, 'min_amount': 0},

    # ── 부자재비 ──
    {'id': 10, 'fee_name': '아이스박스(소)', 'category': 'material', 'amount': 1500,
     'conditions': {}, 'formula': '{base_amount} * {qty}',
     'applies_to': 'all', 'priority': 100, 'is_stackable': True, 'is_active': True, 'min_amount': 0},
    {'id': 11, 'fee_name': '아이스박스(중)', 'category': 'material', 'amount': 2500,
     'conditions': {}, 'formula': '{base_amount} * {qty}',
     'applies_to': 'all', 'priority': 100, 'is_stackable': True, 'is_active': True, 'min_amount': 0},
    {'id': 12, 'fee_name': '아이스팩', 'category': 'material', 'amount': 300,
     'conditions': {}, 'formula': '{base_amount} * {qty}',
     'applies_to': 'all', 'priority': 100, 'is_stackable': True, 'is_active': True, 'min_amount': 0},
    {'id': 13, 'fee_name': '드라이아이스', 'category': 'material', 'amount': 500,
     'conditions': {}, 'formula': '{base_amount} * {qty}',
     'applies_to': 'all', 'priority': 100, 'is_stackable': True, 'is_active': True, 'min_amount': 0},

    # ── 택배비 ──
    {'id': 20, 'fee_name': '기본택배비', 'category': 'courier', 'amount': 3500,
     'conditions': {}, 'formula': '3500',
     'applies_to': 'all', 'priority': 100, 'is_stackable': True, 'is_active': True, 'min_amount': 0},
]


def print_result(title, fees):
    print(f'\n{"="*60}')
    print(f'  {title}')
    print(f'{"="*60}')
    total = 0
    for f in fees:
        amt = f['total_amount']
        total += amt
        detail = f.get('formula_detail', '')
        short_detail = detail.split(' [')[0] if detail else ''
        print(f"  {f['category']:10s} | {f['fee_name']:20s} | {amt:>10,.0f}원 | {short_detail}")
    print(f'  {"":10s} | {"합계":20s} | {total:>10,.0f}원')
    print()


# ═══════════════════════════════════════════
# 출고작업 A
# 아이스박스(소), 아이스팩x2, 드라이아이스x1
# 기본작업비, 동종포장3개, 합포장3개
# ═══════════════════════════════════════════
print('\n' + '#'*60)
print('# 출고작업 A')
print('# 아이스박스(소), 아이스팩x2, 드라이아이스x1')
print('# 기본작업비, 동종포장3개, 합포장3개')
print('#'*60)

# 1) 출고비 계산
outbound_rates = [r for r in client_rates if r['category'] == 'outbound']
fees_a_out = calculate_fees(outbound_rates, {
    'pack_type': 'single',
    'item_count': 3,           # 합포장 3개 (서로 다른 품목)
    'same_item_count': 3,      # 동종포장 3개 (같은 품목)
    'multi_item_count': 3,     # 합포장 3개
    'chargeable_weight_kg': 3.0,
    'qty': 1,
})

# 2) 부자재비 계산 (각 부자재별 개별 호출)
material_rates = [r for r in client_rates if r['category'] == 'material']

# 아이스박스(소) x1
fees_a_box = calculate_fees(
    [r for r in material_rates if r['fee_name'] == '아이스박스(소)'],
    {'qty': 1})

# 아이스팩 x2
fees_a_ice = calculate_fees(
    [r for r in material_rates if r['fee_name'] == '아이스팩'],
    {'qty': 2})

# 드라이아이스 x1
fees_a_dry = calculate_fees(
    [r for r in material_rates if r['fee_name'] == '드라이아이스'],
    {'qty': 1})

# 3) 택배비
courier_rates = [r for r in client_rates if r['category'] == 'courier']
fees_a_courier = calculate_fees(courier_rates, {
    'chargeable_weight_kg': 3.0,
    'delivery_region': '서울',
    'qty': 1,
})

all_fees_a = fees_a_out + fees_a_box + fees_a_ice + fees_a_dry + fees_a_courier
print_result('출고작업 A 과금 내역', all_fees_a)


# ═══════════════════════════════════════════
# 출고작업 B
# 아이스박스(중), 아이스팩x2, 드라이아이스x1
# 기본작업비(중형), 동종포장2개, 합포장10개
# ═══════════════════════════════════════════
print('#'*60)
print('# 출고작업 B')
print('# 아이스박스(중), 아이스팩x2, 드라이아이스x1')
print('# 기본작업비(중형), 동종포장2개, 합포장10개')
print('#'*60)

# 1) 출고비 - 중형 (weight > 5kg이므로 기본작업비(중형) 800원 적용)
fees_b_out = calculate_fees(outbound_rates, {
    'pack_type': 'single',
    'item_count': 10,          # 합포장 10개
    'same_item_count': 2,      # 동종포장 2개
    'multi_item_count': 10,    # 합포장 10개
    'chargeable_weight_kg': 8.0,  # 중형이니 무거움
    'weight_g': 8000,
    'qty': 1,
})

# 2) 부자재비
# 아이스박스(중) x1
fees_b_box = calculate_fees(
    [r for r in material_rates if r['fee_name'] == '아이스박스(중)'],
    {'qty': 1})

# 아이스팩 x2
fees_b_ice = calculate_fees(
    [r for r in material_rates if r['fee_name'] == '아이스팩'],
    {'qty': 2})

# 드라이아이스 x1
fees_b_dry = calculate_fees(
    [r for r in material_rates if r['fee_name'] == '드라이아이스'],
    {'qty': 1})

# 3) 택배비
fees_b_courier = calculate_fees(courier_rates, {
    'chargeable_weight_kg': 8.0,
    'delivery_region': '서울',
    'qty': 1,
})

all_fees_b = fees_b_out + fees_b_box + fees_b_ice + fees_b_dry + fees_b_courier
print_result('출고작업 B 과금 내역', all_fees_b)


# ═══ 비교 요약 ═══
total_a = sum(f['total_amount'] for f in all_fees_a)
total_b = sum(f['total_amount'] for f in all_fees_b)
print('='*60)
print(f'  출고작업 A 합계: {total_a:>10,.0f}원')
print(f'  출고작업 B 합계: {total_b:>10,.0f}원')
print(f'  차이:           {total_b - total_a:>+10,.0f}원')
print('='*60)
