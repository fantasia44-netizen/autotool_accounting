"""3PL 고객사 과금 자동 기록 서비스."""
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _log_fee_safe(billing_repo, data, dedupe_key=None):
    """중복방지 과금 기록. dedupe_key가 있으면 중복 체크 후 insert.

    Returns:
        inserted/existing row dict.
    """
    if dedupe_key:
        data['dedupe_key'] = dedupe_key
        existing = billing_repo.find_by_dedupe_key(data['client_id'], dedupe_key)
        if existing:
            logger.info('중복 과금 스킵: %s', dedupe_key)
            return existing
    return billing_repo.log_fee(data)


def _minute_ts():
    """현재 시각을 분 단위로 truncate한 문자열 반환."""
    return datetime.now(timezone.utc).strftime('%Y%m%d%H%M')


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


def record_inbound_fee(billing_repo, rate_repo, client_id, quantity=1, memo='',
                       sku_id=None):
    """입고 시 입고비 자동 기록."""
    try:
        rates = _get_client_rates_by_category(rate_repo, client_id, 'inbound')
        year_month = _check_invoice_open(billing_repo, client_id, _current_year_month())
        ts_min = _minute_ts()
        for rate in rates:
            unit_price = float(rate.get('amount', 0))
            fee_name = rate.get('fee_name', '입고비')
            # dedupe: inbound:{sku_id}:{quantity}:{timestamp_minute}
            dedupe = f"inbound:{sku_id}:{quantity}:{ts_min}" if sku_id else None
            _log_fee_safe(billing_repo, {
                'client_id': client_id,
                'rate_id': rate.get('id'),
                'year_month': year_month,
                'fee_name': fee_name,
                'category': 'inbound',
                'quantity': quantity,
                'unit_price': unit_price,
                'total_amount': unit_price * quantity,
                'memo': memo,
            }, dedupe_key=dedupe)
    except Exception as e:
        logger.exception('입고비 과금 실패: client_id=%s', client_id)
        _log_billing_failure(billing_repo, client_id, 'inbound',
                             {'quantity': quantity, 'memo': memo}, e)


def record_outbound_fee(billing_repo, rate_repo, client_id, order_id=None,
                        item_count=1, total_weight_g=0, memo=''):
    """출고 시 출고비 + 택배비 자동 기록.

    Args:
        item_count: 주문 내 품목 수 (2개 이상이면 합포장추가비 적용)
        total_weight_g: 총 중량(g) (5kg 초과 시 중량추가비 적용)
    """
    try:
        year_month = _check_invoice_open(billing_repo, client_id, _current_year_month())
        for category in ('outbound', 'courier'):
            rates = _get_client_rates_by_category(rate_repo, client_id, category)
            for rate in rates:
                fee_name = rate.get('fee_name', '')
                unit_price = float(rate.get('amount', 0))
                if unit_price <= 0:
                    continue

                # 조건부 과금: 합포장추가비
                if '합포장' in fee_name:
                    if item_count < 2:
                        continue  # 단품이면 스킵
                    qty = item_count - 1  # 추가 품목 수만큼
                # 조건부 과금: 중량추가비
                elif '중량' in fee_name:
                    extra_kg = (total_weight_g - 5000) / 1000 if total_weight_g > 5000 else 0
                    if extra_kg <= 0:
                        continue
                    qty = int(extra_kg) + (1 if extra_kg % 1 > 0 else 0)  # 올림
                else:
                    qty = 1

                # dedupe: outbound:{order_id}:{category}:{fee_name}
                dedupe = f"outbound:{order_id}:{category}:{fee_name}" if order_id else None
                _log_fee_safe(billing_repo, {
                    'client_id': client_id,
                    'rate_id': rate.get('id'),
                    'order_id': order_id,
                    'year_month': year_month,
                    'fee_name': fee_name,
                    'category': category,
                    'quantity': qty,
                    'unit_price': unit_price,
                    'total_amount': unit_price * qty,
                    'memo': memo,
                }, dedupe_key=dedupe)
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
            # dedupe: packing:{order_id}:{fee_name}
            dedupe = f"packing:{order_id}:{fee_name}" if order_id else None
            _log_fee_safe(billing_repo, {
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
            }, dedupe_key=dedupe)
    except Exception as e:
        logger.exception('부자재비 과금 실패: client_id=%s, order_id=%s', client_id, order_id)
        _log_billing_failure(billing_repo, client_id, 'material',
                             {'order_id': order_id, 'materials': materials, 'memo': memo}, e)


def record_return_fee(billing_repo, rate_repo, client_id, quantity=1, memo=''):
    """반품 시 반품비 기록. quantity: 반품 수량."""
    try:
        rates = _get_client_rates_by_category(rate_repo, client_id, 'return')
        year_month = _check_invoice_open(billing_repo, client_id, _current_year_month())
        ts_min = _minute_ts()
        for rate in rates:
            unit_price = float(rate.get('amount', 0))
            if unit_price <= 0:
                continue
            fee_name = rate.get('fee_name', '반품비')
            # 반품검수비는 수량 기반, 반품수수료는 건당
            qty = quantity if '검수' in fee_name else 1
            # dedupe: return:{client_id}:{timestamp_minute}:{fee_name}
            dedupe = f"return:{client_id}:{ts_min}:{fee_name}"
            _log_fee_safe(billing_repo, {
                'client_id': client_id,
                'rate_id': rate.get('id'),
                'year_month': year_month,
                'fee_name': fee_name,
                'category': 'return',
                'quantity': qty,
                'unit_price': unit_price,
                'total_amount': unit_price * qty,
                'memo': memo,
            }, dedupe_key=dedupe)
    except Exception as e:
        logger.exception('반품비 과금 실패: client_id=%s', client_id)
        _log_billing_failure(billing_repo, client_id, 'return',
                             {'quantity': quantity, 'memo': memo}, e)


def record_vas_fee(billing_repo, rate_repo, client_id, vas_name, quantity=1,
                   order_id=None, memo=''):
    """VAS(부가서비스) 수동 과금. vas_name: 라벨부착/키팅/사진촬영 등."""
    try:
        rates = _get_client_rates_by_category(rate_repo, client_id, 'vas')
        year_month = _check_invoice_open(billing_repo, client_id, _current_year_month())
        matched = None
        for rate in rates:
            if rate.get('fee_name') == vas_name:
                matched = rate
                break
        if not matched:
            logger.warning('VAS 요금표 미등록: client=%s, vas=%s', client_id, vas_name)
            return
        unit_price = float(matched.get('amount', 0))
        if unit_price <= 0:
            return
        # dedupe: vas:{client_id}:{vas_name}:{timestamp_minute}
        ts_min = _minute_ts()
        dedupe = f"vas:{client_id}:{vas_name}:{ts_min}"
        _log_fee_safe(billing_repo, {
            'client_id': client_id,
            'rate_id': matched.get('id'),
            'order_id': order_id,
            'year_month': year_month,
            'fee_name': vas_name,
            'category': 'vas',
            'quantity': quantity,
            'unit_price': unit_price,
            'total_amount': unit_price * quantity,
            'memo': memo,
        }, dedupe_key=dedupe)
    except Exception as e:
        logger.exception('VAS 과금 실패: client_id=%s, vas=%s', client_id, vas_name)
        _log_billing_failure(billing_repo, client_id, 'vas',
                             {'vas_name': vas_name, 'quantity': quantity, 'memo': memo}, e)


def _get_month_days(year_month):
    """year_month(YYYY-MM)의 실제 일수 반환."""
    import calendar
    y, m = int(year_month[:4]), int(year_month[5:7])
    return calendar.monthrange(y, m)[1]


def _match_storage_rate(rates, storage_temp):
    """온도구간에 맞는 보관비 rate 찾기. 없으면 첫번째(일반) 반환."""
    temp_keywords = {
        'cold': ['냉장'],
        'chilled': ['냉장'],     # DB에 chilled로 저장된 경우
        'frozen': ['냉동'],
        'ambient': ['일반', '상온'],
    }
    keywords = temp_keywords.get(storage_temp, ['일반', '상온'])
    for rate in rates:
        fee_name = rate.get('fee_name', '')
        if any(kw in fee_name for kw in keywords):
            return rate
    return rates[0] if rates else None


def calculate_storage_fee(billing_repo, rate_repo, inv_repo, client_id, year_month,
                          force=False):
    """월말 보관비 일괄 계산 — 온도구간별 분리 + 실제일수.

    Args:
        force: True이면 기존 보관비 삭제 후 재계산.
    """
    try:
        # 중복 계산 방지
        existing = billing_repo.list_fees(client_id, year_month=year_month, category='storage')
        if existing and not force:
            logger.info('보관비 이미 계산됨: client=%s, month=%s (%d건)',
                        client_id, year_month, len(existing))
            return {'status': 'already_calculated', 'count': len(existing)}
        if existing and force:
            # 기존 보관비 로그 삭제 후 재계산
            for fee in existing:
                try:
                    billing_repo.delete_fee(fee['id'])
                except Exception:
                    pass
            logger.info('보관비 재계산: client=%s, month=%s (기존 %d건 삭제)',
                        client_id, year_month, len(existing))

        rates = _get_client_rates_by_category(rate_repo, client_id, 'storage')
        if not rates:
            return {'status': 'no_rates'}
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
            temp_label = {'ambient': '상온', 'cold': '냉장', 'chilled': '냉장', 'frozen': '냉동'}.get(
                storage_temp, storage_temp)
            fee_name = rate.get('fee_name', f'{temp_label}보관비')
            # dedupe: storage:{client_id}:{year_month}:{fee_name}
            dedupe = f"storage:{client_id}:{year_month}:{fee_name}"
            _log_fee_safe(billing_repo, {
                'client_id': client_id,
                'year_month': year_month,
                'rate_id': rate.get('id'),
                'fee_name': fee_name,
                'category': 'storage',
                'quantity': total_qty * days,
                'unit_price': unit_price,
                'total_amount': total,
                'memo': f'{temp_label} {total_qty}개 × {days}일',
            }, dedupe_key=dedupe)
        return {'status': 'ok', 'temp_qty': temp_qty, 'days': days}
    except Exception as e:
        logger.exception('보관비 과금 실패: client_id=%s, year_month=%s', client_id, year_month)
        _log_billing_failure(billing_repo, client_id, 'storage',
                             {'year_month': year_month}, e)
        return {'status': 'error', 'error': str(e)}


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
