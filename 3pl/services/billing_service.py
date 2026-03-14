"""과금 서비스 — 사용량 집계, 청구서 생성."""
from db_utils import get_repo


class BillingService:

    @staticmethod
    def record_usage(operator_id, year_month, metric, count):
        """사용량 기록 (건당 과금 메트릭)."""
        repo = get_repo('billing')
        repo.log_usage({
            'operator_id': operator_id,
            'year_month': year_month,
            'metric': metric,
            'count': count,
        })

    @staticmethod
    def generate_invoice(operator_id, year_month):
        """월간 청구서 생성."""
        repo = get_repo('billing')
        usage = repo.get_monthly_usage(operator_id, year_month)

        total = 0
        for u in usage:
            total += u.get('count', 0) * u.get('unit_price', 0)

        return repo.create_invoice({
            'operator_id': operator_id,
            'year_month': year_month,
            'total_amount': total,
            'status': 'pending',
        })
