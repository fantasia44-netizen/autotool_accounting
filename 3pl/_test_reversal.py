"""
역분개(cancel_billing_event) 시뮬레이션 테스트.

실행: python _test_reversal.py
DB 불필요 — fake repository로 로직만 검증.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))


class FakeBillingRepo:
    """DB 없이 billing_engine 로직을 테스트하기 위한 fake repository."""

    def __init__(self):
        self._logs = []
        self._id_seq = 1

    def log_fee(self, data):
        data['id'] = self._id_seq
        self._id_seq += 1
        self._logs.append(dict(data))
        return data

    def find_by_dedupe_key(self, client_id, dedupe_key):
        for row in self._logs:
            if row.get('client_id') == client_id and row.get('dedupe_key') == dedupe_key:
                return row
        return None

    def list_fees(self, client_id, year_month=None, category=None, limit=500):
        result = [r for r in self._logs if r.get('client_id') == client_id]
        if year_month:
            result = [r for r in result if r.get('year_month') == year_month]
        if category:
            result = [r for r in result if r.get('category') == category]
        return result[:limit]


def test_basic_reversal():
    """기본 역분개: 과금 3건 → 역분개 → 합산 0원."""
    from services.billing_engine import cancel_billing_event

    repo = FakeBillingRepo()
    client_id = 'client_001'

    # 원본 과금 3건 기록
    for i in range(3):
        repo.log_fee({
            'client_id': client_id,
            'fee_name': f'출고작업비_{i}',
            'category': 'outbound',
            'unit_price': 300,
            'quantity': 1,
            'total_amount': 300,
            'dedupe_key': f'OUT:order_{i}',
            'year_month': '2026-03',
        })

    assert len(repo._logs) == 3, f'과금 3건 기대, 실제 {len(repo._logs)}'

    # 역분개 실행
    result = cancel_billing_event(repo, client_id, 'OUT:')
    assert result['reversed'] == 3, f'역분개 3건 기대, 실제 {result["reversed"]}'
    assert result['skipped'] == 0
    assert result['total_reversed'] == 900.0

    # 총 6건 (원본 3 + 역분개 3)
    all_fees = repo.list_fees(client_id)
    assert len(all_fees) == 6, f'총 6건 기대, 실제 {len(all_fees)}'

    # 합산 = 0
    total = sum(float(f.get('total_amount', 0)) for f in all_fees)
    assert total == 0, f'합산 0원 기대, 실제 {total}'

    print('  [PASS] 기본 역분개: 3건 → 역분개 3건 → 합산 0원')


def test_idempotent_reversal():
    """멱등성: 같은 역분개를 2번 호출해도 중복 생성 안됨."""
    from services.billing_engine import cancel_billing_event

    repo = FakeBillingRepo()
    client_id = 'client_002'

    repo.log_fee({
        'client_id': client_id,
        'fee_name': '보관비',
        'category': 'storage',
        'unit_price': 500,
        'quantity': 1,
        'total_amount': 500,
        'dedupe_key': 'STR:month_2026-03',
        'year_month': '2026-03',
    })

    # 1차 역분개
    r1 = cancel_billing_event(repo, client_id, 'STR:')
    assert r1['reversed'] == 1

    # 2차 역분개 (멱등 — 이미 처리됨)
    r2 = cancel_billing_event(repo, client_id, 'STR:')
    assert r2['reversed'] == 0, f'멱등성 실패: 2차에서 {r2["reversed"]}건 역분개됨'
    assert r2['skipped'] == 1

    # 총 2건만 (원본 1 + 역분개 1)
    all_fees = repo.list_fees(client_id)
    assert len(all_fees) == 2, f'총 2건 기대, 실제 {len(all_fees)}'

    print('  [PASS] 멱등성: 2차 호출 시 중복 생성 안됨')


def test_partial_prefix():
    """prefix 필터링: 특정 prefix만 역분개."""
    from services.billing_engine import cancel_billing_event

    repo = FakeBillingRepo()
    client_id = 'client_003'

    # 출고 과금 2건
    repo.log_fee({
        'client_id': client_id, 'fee_name': '출고A',
        'category': 'outbound', 'unit_price': 300, 'quantity': 1,
        'total_amount': 300, 'dedupe_key': 'OUT:order_A', 'year_month': '2026-03',
    })
    repo.log_fee({
        'client_id': client_id, 'fee_name': '출고B',
        'category': 'outbound', 'unit_price': 300, 'quantity': 1,
        'total_amount': 300, 'dedupe_key': 'OUT:order_B', 'year_month': '2026-03',
    })
    # 입고 과금 1건
    repo.log_fee({
        'client_id': client_id, 'fee_name': '입고C',
        'category': 'inbound', 'unit_price': 200, 'quantity': 1,
        'total_amount': 200, 'dedupe_key': 'IN:order_C', 'year_month': '2026-03',
    })

    # OUT: prefix만 역분개
    result = cancel_billing_event(repo, client_id, 'OUT:')
    assert result['reversed'] == 2, f'OUT 2건만 역분개 기대, 실제 {result["reversed"]}'

    # IN: 과금은 그대로
    all_fees = repo.list_fees(client_id)
    in_fees = [f for f in all_fees if f.get('category') == 'inbound' and not f.get('is_reversal')]
    assert len(in_fees) == 1, '입고 과금은 유지되어야 함'
    assert float(in_fees[0]['total_amount']) == 200

    print('  [PASS] prefix 필터: OUT만 역분개, IN은 유지')


def test_no_target():
    """대상 없는 역분개: 에러 없이 0건 반환."""
    from services.billing_engine import cancel_billing_event

    repo = FakeBillingRepo()
    result = cancel_billing_event(repo, 'nonexistent_client', 'WHATEVER:')
    assert result['reversed'] == 0
    assert result['skipped'] == 0

    print('  [PASS] 대상 없는 역분개: 에러 없이 0건')


def test_reversal_excluded_from_re_reversal():
    """역분개 레코드는 재역분개 대상에서 제외."""
    from services.billing_engine import cancel_billing_event

    repo = FakeBillingRepo()
    client_id = 'client_005'

    repo.log_fee({
        'client_id': client_id, 'fee_name': '출고비',
        'category': 'outbound', 'unit_price': 300, 'quantity': 1,
        'total_amount': 300, 'dedupe_key': 'OUT:test1', 'year_month': '2026-03',
    })

    # 역분개 실행
    r1 = cancel_billing_event(repo, client_id, 'OUT:')
    assert r1['reversed'] == 1

    # 역분개 레코드의 dedupe_key는 'REV:OUT:test1'
    # 'REV:' prefix로 역분개 시도 → is_reversal=True라 대상에서 제외
    r2 = cancel_billing_event(repo, client_id, 'REV:')
    assert r2['reversed'] == 0, '역분개 레코드는 재역분개 대상이 아님'

    print('  [PASS] 역분개 레코드는 재역분개 대상 제외')


if __name__ == '__main__':
    print('\n=== PackFlow 역분개 시뮬레이션 테스트 ===\n')
    test_basic_reversal()
    test_idempotent_reversal()
    test_partial_prefix()
    test_no_target()
    test_reversal_excluded_from_re_reversal()
    print('\n=== 전체 PASS ===\n')
