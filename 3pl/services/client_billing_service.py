"""3PL 고객사 과금 자동 기록 서비스."""
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _log_billing_failure(billing_repo, client_id, event_type, event_data, error):
    """과금 실패 시 failed_billing_events에 기록 (DLQ).

    이 함수 자체가 실패하면 로그만 남기고 무시한다.
    """
    try:
        from flask import g
        operator_id = getattr(g, 'operator_id', None)
        if not operator_id:
            logger.error('failed_billing_events 기록 불가: operator_id 없음')
            return
        billing_repo._insert('failed_billing_events', {
            'operator_id': operator_id,
            'client_id': client_id,
            'event_type': event_type,
            'event_data': json.dumps(event_data, ensure_ascii=False, default=str),
            'error_message': str(error),
            'status': 'pending',
        })
        logger.warning('과금 실패 이벤트 기록됨: type=%s, client=%s', event_type, client_id)
    except Exception:
        logger.exception('failed_billing_events 기록 자체 실패: type=%s', event_type)


def _current_year_month():
    return datetime.now(timezone.utc).strftime('%Y-%m')


def _get_client_rates_by_category(rate_repo, client_id, category):
    """고객사의 특정 카테고리 요금표 조회."""
    rates = rate_repo.list_rates(client_id) or []
    return [r for r in rates if r.get('category') == category]


def _check_invoice_open(billing_repo, client_id, year_month):
    """정산서가 확정된 월이면 과금 차단. 다음 달로 이월 year_month 반환."""
    invoice = billing_repo.get_invoice(client_id, year_month)
    if invoice and invoice.get('status') not in ('draft', None):
        # 확정/발송/입금완료 상태 → 다음 달로 이월
        y, m = int(year_month[:4]), int(year_month[5:7])
        m += 1
        if m > 12:
            y, m = y + 1, 1
        next_month = f'{y:04d}-{m:02d}'
        logger.warning('정산서 확정 월 과금 이월: client=%s %s→%s',
                       client_id, year_month, next_month)
        return next_month
    return year_month


def record_inbound_fee(billing_repo, rate_repo, client_id, quantity=1, memo=''):
    """입고 시 입고비 자동 기록."""
    try:
        rates = _get_client_rates_by_category(rate_repo, client_id, 'inbound')
        year_month = _check_invoice_open(billing_repo, client_id, _current_year_month())
        for rate in rates:
            unit_price = float(rate.get('amount', 0))
            billing_repo.log_fee({
                'client_id': client_id,
                'rate_id': rate.get('id'),
                'year_month': year_month,
                'fee_name': rate.get('fee_name', '입고비'),
                'category': 'inbound',
                'quantity': quantity,
                'unit_price': unit_price,
                'total_amount': unit_price * quantity,
                'memo': memo,
            })
    except Exception as e:
        logger.exception('입고비 과금 실패: client_id=%s', client_id)
        _log_billing_failure(billing_repo, client_id, 'inbound',
                             {'quantity': quantity, 'memo': memo}, e)


def record_outbound_fee(billing_repo, rate_repo, client_id, order_id=None, memo=''):
    """출고 시 출고비 + 택배비 자동 기록."""
    try:
        year_month = _check_invoice_open(billing_repo, client_id, _current_year_month())
        for category in ('outbound', 'courier'):
            rates = _get_client_rates_by_category(rate_repo, client_id, category)
            for rate in rates:
                unit_price = float(rate.get('amount', 0))
                billing_repo.log_fee({
                    'client_id': client_id,
                    'rate_id': rate.get('id'),
                    'order_id': order_id,
                    'year_month': year_month,
                    'fee_name': rate.get('fee_name'),
                    'category': category,
                    'quantity': 1,
                    'unit_price': unit_price,
                    'total_amount': unit_price,
                    'memo': memo,
                })
    except Exception as e:
        logger.exception('출고비 과금 실패: client_id=%s, order_id=%s', client_id, order_id)
        _log_billing_failure(billing_repo, client_id, 'outbound',
                             {'order_id': order_id, 'memo': memo}, e)


def record_packing_fee(billing_repo, rate_repo, client_id, order_id=None,
                       materials=None, memo=''):
    """패킹 시 부자재비 기록. materials: dict {material_name: qty}"""
    try:
        rates = _get_client_rates_by_category(rate_repo, client_id, 'material')
        year_month = _check_invoice_open(billing_repo, client_id, _current_year_month())
        if not materials:
            materials = {}
        for rate in rates:
            fee_name = rate.get('fee_name', '')
            qty = materials.get(fee_name, 0)
            if qty <= 0:
                continue
            unit_price = float(rate.get('amount', 0))
            billing_repo.log_fee({
                'client_id': client_id,
                'rate_id': rate.get('id'),
                'order_id': order_id,
                'year_month': year_month,
                'fee_name': fee_name,
                'category': 'material',
                'quantity': qty,
                'unit_price': unit_price,
                'total_amount': unit_price * qty,
                'memo': memo,
            })
    except Exception as e:
        logger.exception('부자재비 과금 실패: client_id=%s, order_id=%s', client_id, order_id)
        _log_billing_failure(billing_repo, client_id, 'material',
                             {'order_id': order_id, 'materials': materials, 'memo': memo}, e)


def record_return_fee(billing_repo, rate_repo, client_id, memo=''):
    """반품 시 반품비 기록."""
    try:
        rates = _get_client_rates_by_category(rate_repo, client_id, 'return')
        year_month = _check_invoice_open(billing_repo, client_id, _current_year_month())
        for rate in rates:
            unit_price = float(rate.get('amount', 0))
            billing_repo.log_fee({
                'client_id': client_id,
                'rate_id': rate.get('id'),
                'year_month': year_month,
                'fee_name': rate.get('fee_name', '반품비'),
                'category': 'return',
                'quantity': 1,
                'unit_price': unit_price,
                'total_amount': unit_price,
                'memo': memo,
            })
    except Exception as e:
        logger.exception('반품비 과금 실패: client_id=%s', client_id)
        _log_billing_failure(billing_repo, client_id, 'return',
                             {'memo': memo}, e)


def _get_month_days(year_month):
    """year_month(YYYY-MM)의 실제 일수 반환."""
    import calendar
    y, m = int(year_month[:4]), int(year_month[5:7])
    return calendar.monthrange(y, m)[1]


def _match_storage_rate(rates, storage_temp):
    """온도구간에 맞는 보관비 rate 찾기. 없으면 첫번째(일반) 반환."""
    temp_keywords = {
        'cold': ['냉장'],
        'frozen': ['냉동'],
        'ambient': ['일반', '상온'],
    }
    keywords = temp_keywords.get(storage_temp, ['일반', '상온'])
    for rate in rates:
        fee_name = rate.get('fee_name', '')
        if any(kw in fee_name for kw in keywords):
            return rate
    return rates[0] if rates else None


def calculate_storage_fee(billing_repo, rate_repo, inv_repo, client_id, year_month):
    """월말 보관비 일괄 계산 — 온도구간별 분리 + 실제일수."""
    try:
        rates = _get_client_rates_by_category(rate_repo, client_id, 'storage')
        if not rates:
            return
        days = _get_month_days(year_month)

        # SKU별 재고를 온도구간별로 합산
        skus = inv_repo.list_skus(client_id=client_id) or []
        temp_qty = {}  # {'ambient': N, 'cold': N, 'frozen': N}
        for sku in skus:
            st = sku.get('storage_temp', 'ambient') or 'ambient'
            stocks = inv_repo.list_stock(sku_id=sku['id']) or []
            for stock in stocks:
                qty = stock.get('quantity', 0)
                if qty > 0:
                    temp_qty[st] = temp_qty.get(st, 0) + qty

        # 온도구간별 과금
        for storage_temp, total_qty in temp_qty.items():
            if total_qty <= 0:
                continue
            rate = _match_storage_rate(rates, storage_temp)
            if not rate:
                continue
            unit_price = float(rate.get('amount', 0))
            total = unit_price * total_qty * days
            temp_label = {'ambient': '상온', 'cold': '냉장', 'frozen': '냉동'}.get(
                storage_temp, storage_temp)
            billing_repo.log_fee({
                'client_id': client_id,
                'year_month': year_month,
                'rate_id': rate.get('id'),
                'fee_name': rate.get('fee_name', f'{temp_label}보관비'),
                'category': 'storage',
                'quantity': total_qty * days,
                'unit_price': unit_price,
                'total_amount': total,
                'memo': f'{temp_label} {total_qty}개 × {days}일',
            })
    except Exception as e:
        logger.exception('보관비 과금 실패: client_id=%s, year_month=%s', client_id, year_month)
        _log_billing_failure(billing_repo, client_id, 'storage',
                             {'year_month': year_month}, e)


# ── 과금 프리셋 ──

RATE_PRESETS = [
    {'category': 'inbound', 'fee_name': '입고검수비', 'fee_type': 'fixed', 'unit_label': '건', 'amount': 0},
    {'category': 'inbound', 'fee_name': '상차비', 'fee_type': 'fixed', 'unit_label': '팔레트', 'amount': 0},
    {'category': 'inbound', 'fee_name': '하차비', 'fee_type': 'fixed', 'unit_label': '팔레트', 'amount': 0},
    {'category': 'outbound', 'fee_name': '출고작업비', 'fee_type': 'fixed', 'unit_label': '건', 'amount': 0},
    {'category': 'outbound', 'fee_name': '합포장추가비', 'fee_type': 'fixed', 'unit_label': '건', 'amount': 0},
    {'category': 'storage', 'fee_name': '일반보관비', 'fee_type': 'fixed', 'unit_label': '일', 'amount': 0},
    {'category': 'storage', 'fee_name': '냉장보관비', 'fee_type': 'fixed', 'unit_label': '일', 'amount': 0},
    {'category': 'storage', 'fee_name': '냉동보관비', 'fee_type': 'fixed', 'unit_label': '일', 'amount': 0},
    {'category': 'courier', 'fee_name': '기본택배비', 'fee_type': 'fixed', 'unit_label': '건', 'amount': 0},
    {'category': 'courier', 'fee_name': '사이즈추가비', 'fee_type': 'fixed', 'unit_label': '건', 'amount': 0},
    {'category': 'courier', 'fee_name': '중량추가비', 'fee_type': 'fixed', 'unit_label': 'kg', 'amount': 0},
    {'category': 'material', 'fee_name': '박스', 'fee_type': 'fixed', 'unit_label': '개', 'amount': 0},
    {'category': 'material', 'fee_name': '아이스팩', 'fee_type': 'fixed', 'unit_label': '개', 'amount': 0},
    {'category': 'material', 'fee_name': '드라이아이스', 'fee_type': 'fixed', 'unit_label': '개', 'amount': 0},
    {'category': 'material', 'fee_name': '완충재', 'fee_type': 'fixed', 'unit_label': '개', 'amount': 0},
    {'category': 'material', 'fee_name': '테이프', 'fee_type': 'fixed', 'unit_label': '개', 'amount': 0},
    {'category': 'return', 'fee_name': '반품수수료', 'fee_type': 'fixed', 'unit_label': '건', 'amount': 0},
    {'category': 'return', 'fee_name': '반품검수비', 'fee_type': 'fixed', 'unit_label': '건', 'amount': 0},
    {'category': 'vas', 'fee_name': '라벨부착', 'fee_type': 'fixed', 'unit_label': '건', 'amount': 0},
    {'category': 'vas', 'fee_name': '키팅', 'fee_type': 'fixed', 'unit_label': '건', 'amount': 0},
    {'category': 'vas', 'fee_name': '사진촬영', 'fee_type': 'fixed', 'unit_label': 'SKU', 'amount': 0},
]

CATEGORY_LABELS = {
    'inbound': '입고비',
    'outbound': '출고비',
    'storage': '보관비',
    'courier': '택배비',
    'material': '부자재비',
    'return': '반품비',
    'vas': '부가서비스',
    'custom': '기타',
}
