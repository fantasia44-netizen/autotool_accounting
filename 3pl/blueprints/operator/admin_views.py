"""감사로그 + 경영분석 관련 라우트."""
import logging
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from . import operator_bp, _require_operator

logger = logging.getLogger(__name__)


def _require_admin():
    """admin 이상 권한 체크."""
    if not current_user.is_admin():
        from flask import abort
        abort(403)


# ═══════════════════════════════════════════
# 감사 로그 (Audit Log)
# ═══════════════════════════════════════════

@operator_bp.route('/audit-log')
@login_required
@_require_operator
def audit_log():
    """감사 로그 목록 페이지."""
    _require_admin()
    from db_utils import get_repo
    repo = get_repo('audit')

    table_name = request.args.get('table', '')
    action = request.args.get('action', '')
    record_id = request.args.get('record_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    logs = repo.list_logs(
        table_name=table_name or None,
        action=action or None,
        record_id=record_id or None,
        date_from=date_from or None,
        date_to=date_to or None,
        limit=300,
    )

    # 테이블명 한글 매핑
    table_labels = {
        'clients': '고객사', 'client_rates': '요금표', 'skus': '상품',
        'orders': '주문', 'shipments': '출고', 'packing_jobs': '패킹작업',
        'inbound_receipts': '입고', 'inventory_adjustments': '재고조정',
        'client_billing_logs': '과금로그', 'client_invoices': '정산서',
        'picking_lists': '피킹리스트', 'expenses': '비용',
        'users': '사용자', 'warehouse_zones': '창고구역',
    }

    return render_template('operator/audit_log.html',
                           logs=logs,
                           table_labels=table_labels,
                           filters={
                               'table': table_name,
                               'action': action,
                               'record_id': record_id,
                               'date_from': date_from,
                               'date_to': date_to,
                           })


@operator_bp.route('/audit-log/<int:record_id>/history')
@login_required
@_require_operator
def audit_record_history(record_id):
    """특정 레코드의 변경 이력 (JSON)."""
    _require_admin()
    from db_utils import get_repo
    repo = get_repo('audit')
    table_name = request.args.get('table', '')
    if not table_name:
        return jsonify({'error': 'table parameter required'}), 400
    history = repo.get_record_history(table_name, record_id)
    return jsonify(history)


@operator_bp.route('/audit-log/restore', methods=['POST'])
@login_required
@_require_operator
def audit_restore():
    """soft delete된 레코드 복원."""
    _require_admin()
    from db_utils import get_repo
    from repositories.base import SOFT_DELETE_TABLES

    table_name = request.form.get('table_name', '')
    record_id = request.form.get('record_id', '')

    if not table_name or not record_id:
        flash('복원 대상 정보가 부족합니다.', 'warning')
        return redirect(url_for('operator.audit_log'))

    if table_name not in SOFT_DELETE_TABLES:
        flash(f'{table_name}은 soft delete 대상이 아닙니다.', 'warning')
        return redirect(url_for('operator.audit_log'))

    # 해당 테이블의 repo 찾기 (범용)
    audit_repo = get_repo('audit')
    restored = audit_repo._restore(table_name, int(record_id))
    if restored:
        flash(f'{table_name} #{record_id} 복원 완료', 'success')
    else:
        flash('복원 실패 — 레코드를 찾을 수 없습니다.', 'danger')
    return redirect(url_for('operator.audit_log', table=table_name))


# ═══════════════════════════════════════════
# 경영분석 (Finance / P&L)
# ═══════════════════════════════════════════

@operator_bp.route('/finance')
@login_required
@_require_operator
def finance_dashboard():
    """경영분석 대시보드 — 매출/비용/손익."""
    _require_admin()
    from db_utils import get_repo
    from services.tz_utils import now_kst
    from services.finance_service import EXPENSE_CATEGORIES

    finance_repo = get_repo('finance')
    year_month = request.args.get('month', now_kst().strftime('%Y-%m'))

    # P&L 데이터
    pnl = finance_repo.get_pnl(year_month)

    # 비용 목록
    expenses = finance_repo.list_expenses(year_month=year_month)
    expense_summary = finance_repo.sum_expenses_by_month(year_month)

    # 최근 6개월 추이
    from services.finance_service import get_pnl_trend
    trend = get_pnl_trend(finance_repo, months=6)

    return render_template('operator/finance_dashboard.html',
                           year_month=year_month,
                           pnl=pnl,
                           expenses=expenses,
                           expense_summary=expense_summary,
                           expense_categories=EXPENSE_CATEGORIES,
                           trend=trend)


@operator_bp.route('/finance/recalc', methods=['POST'])
@login_required
@_require_operator
def finance_recalc():
    """P&L 재계산."""
    _require_admin()
    from db_utils import get_repo
    from services.finance_service import calculate_monthly_pnl

    year_month = request.form.get('year_month', '')
    if not year_month:
        flash('월 정보가 필요합니다.', 'warning')
        return redirect(url_for('operator.finance_dashboard'))

    billing_repo = get_repo('client_billing')
    finance_repo = get_repo('finance')
    result = calculate_monthly_pnl(billing_repo, finance_repo, year_month)
    flash(f'{year_month} P&L 재계산 완료 — 매출: {result["revenue"]:,.0f}원, 비용: {result["cost_of_service"] + result["operating_expense"]:,.0f}원', 'success')
    return redirect(url_for('operator.finance_dashboard', month=year_month))


@operator_bp.route('/finance/expense', methods=['POST'])
@login_required
@_require_operator
def finance_expense_create():
    """비용 등록."""
    _require_admin()
    from db_utils import get_repo
    finance_repo = get_repo('finance')

    expense_date = request.form.get('expense_date', '')
    data = {
        'category': request.form.get('category', 'etc'),
        'title': request.form.get('title', '').strip(),
        'description': request.form.get('description', '').strip(),
        'amount': float(request.form.get('amount', 0)),
        'tax_amount': float(request.form.get('tax_amount', 0)),
        'vendor_name': request.form.get('vendor_name', '').strip(),
        'vendor_biz_no': request.form.get('vendor_biz_no', '').strip(),
        'expense_date': expense_date,
        'year_month': expense_date[:7] if expense_date else '',
    }
    finance_repo.create_expense(data)
    flash(f'비용 "{data["title"]}" 등록 완료', 'success')
    return redirect(url_for('operator.finance_dashboard', month=data['year_month']))


@operator_bp.route('/finance/expense/<int:expense_id>/delete', methods=['POST'])
@login_required
@_require_operator
def finance_expense_delete(expense_id):
    """비용 삭제 (soft delete)."""
    _require_admin()
    from db_utils import get_repo
    finance_repo = get_repo('finance')
    expense = finance_repo.get_expense(expense_id)
    if not expense:
        flash('비용을 찾을 수 없습니다.', 'warning')
        return redirect(url_for('operator.finance_dashboard'))
    finance_repo.delete_expense(expense_id)
    flash('비용 삭제 완료', 'success')
    ym = expense.get('year_month', '')
    return redirect(url_for('operator.finance_dashboard', month=ym))


# ═══════════════════════════════════════════
# 작업 KPI 대시보드
# ═══════════════════════════════════════════

@operator_bp.route('/kpi')
@login_required
@_require_operator
def kpi_dashboard():
    """작업 KPI 대시보드 — 모드별 처리량, 작업자 성과."""
    from flask import g
    from db_utils import get_repo
    from services.kpi_service import get_team_kpi, get_billing_queue_status

    date_str = request.args.get('date')
    repo = get_repo('client')

    team_kpi = get_team_kpi(repo.supabase, g.operator_id, date_str)
    billing_status = get_billing_queue_status(repo.supabase, g.operator_id)

    # 작업자 이름 매핑
    user_repo = get_repo('user') if hasattr(get_repo, '__call__') else None
    worker_names = {}
    if user_repo:
        try:
            for uid in team_kpi.get('workers', {}).keys():
                u = user_repo.get_user(uid)
                if u:
                    worker_names[uid] = u.get('name', u.get('username', f'#{uid}'))
        except Exception:
            pass

    return render_template('operator/kpi_dashboard.html',
                           kpi=team_kpi,
                           billing=billing_status,
                           worker_names=worker_names,
                           selected_date=date_str or team_kpi.get('date', ''))
