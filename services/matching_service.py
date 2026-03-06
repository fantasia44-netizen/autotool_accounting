"""
matching_service.py -- 매출-입금 매칭 엔진.

매칭 범위 (현재 + 확장 계획):
1. 세금계산서 ↔ 은행 입금 (Phase 1 - 현재)
2. 플랫폼 정산금 ↔ 은행 입금 (Phase 2 - 플랫폼 API 연동 후)
3. 세금계산서 ↔ 플랫폼 매출 ↔ 은행 입금 3자 매칭 (Phase 3)
"""
import logging

logger = logging.getLogger(__name__)


def auto_match_invoices(db, date_from=None, date_to=None):
    """자동 매칭: 세금계산서(매출) ↔ 은행 입금.

    매칭 기준:
    1. 금액 완전 일치
    2. 거래처명 유사도 매칭

    Returns:
        dict: {matched_count, candidates}
    """
    # 미매칭 매출 세금계산서
    invoices = db.query_tax_invoices(
        direction='sales', status='issued',
        date_from=date_from, date_to=date_to,
        unmatched_only=True,
    )

    # 미매칭 입금 거래
    deposits = db.query_bank_transactions(
        transaction_type='입금',
        date_from=date_from, date_to=date_to,
        unmatched_only=True,
    )

    candidates = []
    used_deposits = set()

    for inv in invoices:
        inv_amount = inv.get('total_amount', 0)
        inv_buyer = inv.get('buyer_corp_name', '')

        for dep in deposits:
            if dep['id'] in used_deposits:
                continue

            dep_amount = dep.get('amount', 0)
            dep_name = dep.get('counterpart_name', '')

            # 금액 완전 일치 + 거래처명 포함
            if inv_amount == dep_amount and _name_match(inv_buyer, dep_name):
                candidates.append({
                    'invoice_id': inv['id'],
                    'transaction_id': dep['id'],
                    'invoice_amount': inv_amount,
                    'transaction_amount': dep_amount,
                    'partner_name': inv_buyer,
                    'bank_name': dep_name,
                    'confidence': 'high',
                })
                used_deposits.add(dep['id'])
                break

    logger.info(f"자동 매칭: {len(candidates)}건 후보 발견")
    return {'matched_count': len(candidates), 'candidates': candidates}


def auto_match_settlements(db, date_from=None, date_to=None):
    """[Phase 2 확장] 플랫폼 정산금 ↔ 은행 입금 자동 매칭.

    정산금은 금액이 정확히 일치하므로 매칭 정확도가 높음.
    """
    # TODO: Phase 2에서 구현
    # settlements = db.query_platform_settlements(
    #     match_status='pending', date_from=date_from, date_to=date_to)
    # deposits = db.query_bank_transactions(
    #     transaction_type='입금', unmatched_only=True, ...)
    return {'matched_count': 0, 'candidates': []}


def confirm_match(db, tax_invoice_id, bank_transaction_id, matched_by=''):
    """매칭 확정 → payment_matches 레코드 생성."""
    inv = db.query_tax_invoice_by_id(tax_invoice_id)
    tx = db.query_bank_transaction_by_id(bank_transaction_id)

    if not inv or not tx:
        raise ValueError('세금계산서 또는 거래내역을 찾을 수 없습니다')

    inv_amount = inv.get('total_amount', 0)
    tx_amount = tx.get('amount', 0)

    payload = {
        'tax_invoice_id': tax_invoice_id,
        'bank_transaction_id': bank_transaction_id,
        'match_type': 'auto',
        'match_status': 'matched' if inv_amount == tx_amount else 'partial',
        'matched_amount': min(inv_amount, tx_amount),
        'invoice_amount': inv_amount,
        'transaction_amount': tx_amount,
        'difference': tx_amount - inv_amount,
        'partner_name': inv.get('buyer_corp_name', ''),
        'matched_by': matched_by,
    }

    db.insert_payment_match(payload)

    # 양쪽에 매칭 ID 업데이트
    db.update_tax_invoice(tax_invoice_id, {'matched_transaction_id': bank_transaction_id})
    db.update_bank_transaction(bank_transaction_id, {'matched_invoice_id': tax_invoice_id})

    logger.info(f"매칭 확정: 세금계산서 {tax_invoice_id} ↔ 거래 {bank_transaction_id}")


def manual_match(db, tax_invoice_id, bank_transaction_id, matched_by=''):
    """수동 매칭."""
    inv = db.query_tax_invoice_by_id(tax_invoice_id)
    tx = db.query_bank_transaction_by_id(bank_transaction_id)

    if not inv or not tx:
        raise ValueError('세금계산서 또는 거래내역을 찾을 수 없습니다')

    inv_amount = inv.get('total_amount', 0)
    tx_amount = tx.get('amount', 0)

    payload = {
        'tax_invoice_id': tax_invoice_id,
        'bank_transaction_id': bank_transaction_id,
        'match_type': 'manual',
        'match_status': 'matched' if inv_amount == tx_amount else 'partial',
        'matched_amount': min(inv_amount, tx_amount),
        'invoice_amount': inv_amount,
        'transaction_amount': tx_amount,
        'difference': tx_amount - inv_amount,
        'partner_name': inv.get('buyer_corp_name', ''),
        'matched_by': matched_by,
    }

    db.insert_payment_match(payload)
    db.update_tax_invoice(tax_invoice_id, {'matched_transaction_id': bank_transaction_id})
    db.update_bank_transaction(bank_transaction_id, {'matched_invoice_id': tax_invoice_id})


def unmatch(db, match_id):
    """매칭 해제."""
    match = db.query_payment_match_by_id(match_id)
    if not match:
        raise ValueError(f'매칭 ID {match_id}를 찾을 수 없습니다')

    # 양쪽 매칭 해제
    if match.get('tax_invoice_id'):
        db.update_tax_invoice(match['tax_invoice_id'], {'matched_transaction_id': None})
    if match.get('bank_transaction_id'):
        db.update_bank_transaction(match['bank_transaction_id'], {'matched_invoice_id': None})

    db.delete_payment_match(match_id)
    logger.info(f"매칭 해제: {match_id}")


def get_receivables(db, as_of_date=None):
    """미수금 현황 (미매칭 매출 세금계산서 거래처별 집계).

    Returns:
        list: [{partner_name, corp_num, total_amount, invoice_count, oldest_date}]
    """
    unmatched = db.query_tax_invoices(
        direction='sales', unmatched_only=True,
    )

    by_partner = {}
    for inv in unmatched:
        name = inv.get('buyer_corp_name', '미지정')
        corp_num = inv.get('buyer_corp_num', '')
        key = corp_num or name

        if key not in by_partner:
            by_partner[key] = {
                'partner_name': name,
                'corp_num': corp_num,
                'total_amount': 0,
                'invoice_count': 0,
                'oldest_date': str(inv.get('write_date', '')),
                'invoices': [],
            }
        by_partner[key]['total_amount'] += inv.get('total_amount', 0)
        by_partner[key]['invoice_count'] += 1
        by_partner[key]['invoices'].append({
            'id': inv['id'],
            'write_date': str(inv.get('write_date', '')),
            'total_amount': inv.get('total_amount', 0),
        })

        wd = str(inv.get('write_date', ''))
        if wd and wd < by_partner[key]['oldest_date']:
            by_partner[key]['oldest_date'] = wd

    return sorted(by_partner.values(), key=lambda x: -x['total_amount'])


def get_matching_summary(db, date_from=None, date_to=None):
    """매칭 현황 요약 (대시보드용).

    Returns:
        dict: {total_invoices, matched_invoices, unmatched_invoices,
               total_deposits, matched_deposits, unmatched_deposits,
               match_rate}
    """
    invoices = db.query_tax_invoices(direction='sales', date_from=date_from, date_to=date_to)
    total_inv = len(invoices)
    matched_inv = sum(1 for i in invoices if i.get('matched_transaction_id'))
    unmatched_inv = total_inv - matched_inv

    deposits = db.query_bank_transactions(
        transaction_type='입금', date_from=date_from, date_to=date_to)
    total_dep = len(deposits)
    matched_dep = sum(1 for d in deposits if d.get('matched_invoice_id'))
    unmatched_dep = total_dep - matched_dep

    match_rate = (matched_inv / total_inv * 100) if total_inv > 0 else 0

    return {
        'total_invoices': total_inv,
        'matched_invoices': matched_inv,
        'unmatched_invoices': unmatched_inv,
        'total_deposits': total_dep,
        'matched_deposits': matched_dep,
        'unmatched_deposits': unmatched_dep,
        'match_rate': round(match_rate, 1),
    }


def _name_match(invoice_name, bank_name):
    """거래처명 유사도 판정 (단순 포함 매칭)."""
    if not invoice_name or not bank_name:
        return False
    # 흔한 법인 표기 제거 후 비교
    clean = lambda s: s.replace(' ', '').replace('(주)', '').replace('주식회사', '').replace('(유)', '')
    a = clean(invoice_name)
    b = clean(bank_name)
    return a in b or b in a
