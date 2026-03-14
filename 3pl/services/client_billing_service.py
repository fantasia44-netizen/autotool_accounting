"""3PL 고객사 과금 자동 기록 서비스."""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


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


def record_outbound_fee(billing_repo, rate_repo, client_id, order_id=None, memo=''):
    """출고 시 출고비 + 택배비 자동 기록."""
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


def record_packing_fee(billing_repo, rate_repo, client_id, order_id=None,
                       materials=None, memo=''):
    """패킹 시 부자재비 기록. materials: dict {material_name: qty}"""
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


def record_return_fee(billing_repo, rate_repo, client_id, memo=''):
    """반품 시 반품비 기록."""
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


def calculate_storage_fee(billing_repo, rate_repo, inv_repo, client_id, year_month):
    """월말 보관비 일괄 계산."""
    rates = _get_client_rates_by_category(rate_repo, client_id, 'storage')
    if not rates:
        return
    # 해당 고객사 재고 수량 합산
    skus = inv_repo.list_skus(client_id=client_id) or []
    total_qty = 0
    for sku in skus:
        stocks = inv_repo.list_stock(sku_id=sku['id']) or []
        for st in stocks:
            total_qty += st.get('quantity', 0)

    for rate in rates:
        unit_price = float(rate.get('amount', 0))
        # 단위에 따라 계산 (일 기준 → 30일)
        days = 30
        total = unit_price * total_qty * days
        billing_repo.log_fee({
            'client_id': client_id,
            'year_month': year_month,
            'rate_id': rate.get('id'),
            'fee_name': rate.get('fee_name', '보관비'),
            'category': 'storage',
            'quantity': total_qty * days,
            'unit_price': unit_price,
            'total_amount': total,
            'memo': f'재고 {total_qty}개 × {days}일',
        })


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
