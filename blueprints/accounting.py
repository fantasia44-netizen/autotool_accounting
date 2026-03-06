"""accounting.py -- 회계 대시보드 / 매출-입금 매칭 Blueprint."""
from flask import Blueprint, render_template, request, current_app, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from auth import role_required, _log_action
from services.tz_utils import today_kst, days_ago_kst

accounting_bp = Blueprint('accounting', __name__, url_prefix='/accounting')


@accounting_bp.route('/')
@role_required('admin', 'ceo', 'manager', 'general')
def dashboard():
    """회계 대시보드"""
    db = current_app.db
    from services.bank_service import get_transaction_summary
    from services.matching_service import get_receivables, get_matching_summary

    today = today_kst()
    month_start = today[:7] + '-01'

    # 이번 달 입출금 요약
    summary = get_transaction_summary(db, date_from=month_start, date_to=today)

    # 미수금 현황
    receivables = get_receivables(db)
    total_receivable = sum(r['total_amount'] for r in receivables)

    # 매칭 현황
    match_summary = get_matching_summary(db, date_from=month_start, date_to=today)

    # 이번 달 매출/매입 세금계산서 합계
    invoices = db.query_tax_invoices(date_from=month_start, date_to=today)
    sales_total = sum(i.get('total_amount', 0) for i in invoices if i.get('direction') == 'sales')
    purchase_total = sum(i.get('total_amount', 0) for i in invoices if i.get('direction') == 'purchase')

    # 플랫폼 정산 현황 (Phase 2 확장 준비)
    settlements = db.query_platform_settlements(date_from=month_start, date_to=today)
    settlement_total = sum(s.get('net_settlement', 0) for s in settlements)
    platform_fee_total = sum(s.get('platform_fee', 0) for s in settlements)

    return render_template('accounting/dashboard.html',
                           summary=summary,
                           receivables=receivables,
                           total_receivable=total_receivable,
                           match_summary=match_summary,
                           sales_total=sales_total,
                           purchase_total=purchase_total,
                           settlement_total=settlement_total,
                           platform_fee_total=platform_fee_total,
                           month_start=month_start,
                           today=today)


@accounting_bp.route('/matching')
@role_required('admin', 'manager', 'general')
def matching():
    """매출-입금 매칭"""
    db = current_app.db
    date_from = request.args.get('date_from', days_ago_kst(30))
    date_to = request.args.get('date_to', today_kst())

    unmatched_invoices = db.query_tax_invoices(
        direction='sales', unmatched_only=True,
        date_from=date_from, date_to=date_to,
    )
    unmatched_deposits = db.query_bank_transactions(
        transaction_type='입금', unmatched_only=True,
        date_from=date_from, date_to=date_to,
    )
    matches = db.query_payment_matches(date_from=date_from, date_to=date_to)

    return render_template('accounting/matching.html',
                           invoices=unmatched_invoices,
                           deposits=unmatched_deposits,
                           matches=matches,
                           date_from=date_from, date_to=date_to)


@accounting_bp.route('/matching/auto', methods=['POST'])
@role_required('admin', 'manager')
def auto_match():
    """자동 매칭 실행"""
    from services.matching_service import auto_match_invoices, confirm_match
    date_from = request.form.get('date_from', days_ago_kst(30))
    date_to = request.form.get('date_to', today_kst())

    try:
        result = auto_match_invoices(current_app.db, date_from, date_to)
        for c in result['candidates']:
            confirm_match(current_app.db, c['invoice_id'], c['transaction_id'],
                          matched_by=current_user.username)
        _log_action('auto_match',
                    detail=f'{result["matched_count"]}건 매칭')
        flash(f'자동 매칭 {result["matched_count"]}건 완료', 'success')
    except Exception as e:
        flash(f'자동 매칭 오류: {e}', 'danger')

    return redirect(url_for('accounting.matching',
                            date_from=date_from, date_to=date_to))


@accounting_bp.route('/matching/manual', methods=['POST'])
@role_required('admin', 'manager', 'general')
def manual_match_action():
    """수동 매칭"""
    from services.matching_service import manual_match
    invoice_id = request.form.get('invoice_id', type=int)
    transaction_id = request.form.get('transaction_id', type=int)

    if not invoice_id or not transaction_id:
        flash('세금계산서와 입금 거래를 선택하세요.', 'danger')
        return redirect(url_for('accounting.matching'))

    try:
        manual_match(current_app.db, invoice_id, transaction_id,
                     matched_by=current_user.username)
        _log_action('manual_match',
                    detail=f'세금계산서 {invoice_id} ↔ 거래 {transaction_id}')
        flash('수동 매칭 완료', 'success')
    except Exception as e:
        flash(f'매칭 오류: {e}', 'danger')

    return redirect(url_for('accounting.matching'))


@accounting_bp.route('/matching/unmatch/<int:match_id>', methods=['POST'])
@role_required('admin', 'manager')
def unmatch_action(match_id):
    """매칭 해제"""
    from services.matching_service import unmatch
    try:
        unmatch(current_app.db, match_id)
        _log_action('unmatch',
                    detail=f'매칭 {match_id} 해제')
        flash('매칭이 해제되었습니다.', 'success')
    except Exception as e:
        flash(f'매칭 해제 오류: {e}', 'danger')
    return redirect(url_for('accounting.matching'))


@accounting_bp.route('/receivables')
@role_required('admin', 'ceo', 'manager', 'general')
def receivables():
    """미수금 관리"""
    from services.matching_service import get_receivables
    items = get_receivables(current_app.db)
    total = sum(r['total_amount'] for r in items)
    return render_template('accounting/receivables.html',
                           receivables=items, total=total)


@accounting_bp.route('/api/dashboard-data')
@role_required('admin', 'ceo', 'manager', 'general')
def api_dashboard_data():
    """대시보드 데이터 JSON (차트 갱신용)"""
    db = current_app.db
    from services.bank_service import get_transaction_summary
    from services.matching_service import get_receivables

    today = today_kst()
    month_start = today[:7] + '-01'

    summary = get_transaction_summary(db, date_from=month_start, date_to=today)
    receivables = get_receivables(db)

    return jsonify({
        'summary': summary,
        'total_receivable': sum(r['total_amount'] for r in receivables),
        'receivable_count': len(receivables),
    })
