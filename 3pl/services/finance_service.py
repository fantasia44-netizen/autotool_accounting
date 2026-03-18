"""경영분석 서비스 — 매출/비용/손익 집계.

3PL 물류 운영사 관점의 P&L:
- 매출: 고객사별 과금 합계 (client_billing_logs)
- 비용: 세금계산서, 인건비, 임대료, 부자재 등 (expenses)
- 손익: 매출 - 비용
"""
from services.tz_utils import now_kst


# 비용 카테고리
EXPENSE_CATEGORIES = {
    'tax_invoice': '세금계산서',
    'labor': '인건비',
    'rent': '임대/관리비',
    'utility': '공과금',
    'supplies': '부자재/소모품',
    'delivery': '배송비',
    'insurance': '보험료',
    'depreciation': '감가상각',
    'etc': '기타',
}


def calculate_monthly_pnl(billing_repo, finance_repo, year_month,
                          client_repo=None):
    """월별 손익계산서 생성/업데이트.

    Args:
        billing_repo: ClientBillingRepository
        finance_repo: FinanceRepository
        year_month: 'YYYY-MM'
        client_repo: ClientRepository (삭제 고객 필터용, 선택)

    Returns:
        dict: P&L 요약
    """
    # ── 매출: 전체 고객사 과금 합계 ──
    try:
        all_billing = billing_repo._query(
            billing_repo.LOG_TABLE,
            filters=[('year_month', 'eq', year_month)],
            limit=5000
        )
    except Exception:
        all_billing = []

    # 삭제된 고객사 과금 제외
    if client_repo:
        try:
            active_clients = client_repo.list_clients() or []
            active_ids = {c['id'] for c in active_clients}
            excluded = len([b for b in all_billing if b.get('client_id') not in active_ids])
            all_billing = [b for b in all_billing if b.get('client_id') in active_ids]
            if excluded:
                import logging
                logging.getLogger(__name__).info(
                    'P&L %s: 삭제 고객 과금 %d건 제외', year_month, excluded)
        except Exception:
            pass  # 필터 실패 시 전체 포함 (안전 우선)

    revenue_by_cat = {}
    revenue_total = 0
    revenue_by_client = {}
    for r in all_billing:
        cat = r.get('category', 'custom')
        amt = float(r.get('total_amount', 0))
        revenue_by_cat[cat] = revenue_by_cat.get(cat, 0) + amt
        revenue_total += amt
        cid = r.get('client_id')
        if cid:
            revenue_by_client[cid] = revenue_by_client.get(cid, 0) + amt

    # ── 비용: expenses 합산 ──
    expense_summary = finance_repo.sum_expenses_by_month(year_month)

    # ── 손익 계산 ──
    expense_total = expense_summary['total']
    gross_profit = revenue_total - expense_total
    # 세부 구분: 원가 vs 판관비
    cost_cats = {'labor', 'supplies', 'delivery'}
    cost_of_service = sum(
        v for k, v in expense_summary['by_category'].items()
        if k in cost_cats
    )
    operating_expense = expense_total - cost_of_service

    pnl_data = {
        'year_month': year_month,
        'revenue': revenue_total,
        'cost_of_service': cost_of_service,
        'operating_expense': operating_expense,
        'gross_profit': revenue_total - cost_of_service,
        'net_income': gross_profit,
        'detail': {
            'revenue_by_category': revenue_by_cat,
            'revenue_by_client': revenue_by_client,
            'expense_by_category': expense_summary['by_category'],
        },
        'calculated_at': now_kst().isoformat(),
    }

    # DB에 upsert
    finance_repo.upsert_pnl(pnl_data)
    return pnl_data


def get_pnl_trend(finance_repo, months=6):
    """최근 N개월 P&L 추이."""
    rows = finance_repo.list_pnl(limit=months)
    return sorted(rows, key=lambda x: x.get('year_month', ''))
