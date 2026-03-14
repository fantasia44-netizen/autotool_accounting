"""고객사/요금/마켓플레이스/과금정산/고객사 SKU 관련 라우트."""
import logging
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from . import operator_bp, _require_operator

logger = logging.getLogger(__name__)


# ═══ 고객사관리 ═══

@operator_bp.route('/clients')
@login_required
@_require_operator
def clients():
    from db_utils import get_repo
    repo = get_repo('client')
    items = repo.list_clients()
    return render_template('operator/clients.html', clients=items)


@operator_bp.route('/clients/new', methods=['POST'])
@login_required
@_require_operator
def client_create():
    from db_utils import get_repo
    repo = get_repo('client')
    data = {
        'name': request.form.get('name', '').strip(),
        'business_no': request.form.get('business_no', '').strip(),
        'contact_name': request.form.get('contact_name', '').strip(),
        'contact_phone': request.form.get('contact_phone', '').strip(),
        'contact_email': request.form.get('contact_email', '').strip(),
        'address': request.form.get('address', '').strip(),
        'memo': request.form.get('memo', '').strip(),
    }
    repo.create_client(data)
    flash(f'고객사 "{data["name"]}" 등록 완료', 'success')
    return redirect(url_for('operator.clients'))


@operator_bp.route('/clients/<int:client_id>')
@login_required
@_require_operator
def client_detail(client_id):
    from db_utils import get_repo
    client_repo = get_repo('client')
    client = client_repo.get_client(client_id)
    if not client:
        flash('고객사를 찾을 수 없습니다.', 'warning')
        return redirect(url_for('operator.clients'))
    rate_repo = get_repo('client_rate')
    rates = rate_repo.list_rates(client_id) or []
    rate_count = len(rates)
    mkt_repo = get_repo('client_marketplace')
    mkt_creds = mkt_repo.list_credentials(client_id) or []
    inv_repo = get_repo('inventory')
    client_skus = inv_repo.list_skus(client_id=client_id) or []
    return render_template('operator/client_detail.html', client=client,
                           rates=rates, rate_count=rate_count,
                           mkt_creds=mkt_creds, client_skus=client_skus)


@operator_bp.route('/clients/<int:client_id>/update', methods=['POST'])
@login_required
@_require_operator
def client_update(client_id):
    from db_utils import get_repo
    repo = get_repo('client')
    data = {
        'name': request.form.get('name', '').strip(),
        'business_no': request.form.get('business_no', '').strip(),
        'contact_name': request.form.get('contact_name', '').strip(),
        'contact_phone': request.form.get('contact_phone', '').strip(),
        'contact_email': request.form.get('contact_email', '').strip(),
        'address': request.form.get('address', '').strip(),
        'memo': request.form.get('memo', '').strip(),
    }
    repo.update_client(client_id, data)
    flash('고객사 정보가 수정되었습니다.', 'success')
    return redirect(url_for('operator.client_detail', client_id=client_id))


# ═══ 고객사 요금표 ═══

@operator_bp.route('/clients/<int:client_id>/rates', methods=['POST'])
@login_required
@_require_operator
def client_rate_create(client_id):
    from db_utils import get_repo
    rate_repo = get_repo('client_rate')
    count = rate_repo.count_rates(client_id)
    if count >= 50:
        flash('요금 항목은 최대 50개까지 등록할 수 있습니다.', 'warning')
        return redirect(url_for('operator.client_detail', client_id=client_id))

    data = {
        'client_id': client_id,
        'fee_name': request.form.get('fee_name', '').strip(),
        'fee_type': request.form.get('fee_type', 'fixed'),
        'amount': request.form.get('amount', 0, type=float),
        'unit_label': request.form.get('unit_label', '건').strip(),
        'category': request.form.get('category', 'custom').strip(),
        'memo': request.form.get('memo', '').strip(),
        'sort_order': count,
    }
    if not data['fee_name']:
        flash('항목명을 입력해주세요.', 'warning')
        return redirect(url_for('operator.client_detail', client_id=client_id))

    rate_repo.create_rate(data)
    flash(f'요금 항목 "{data["fee_name"]}" 추가 완료', 'success')
    return redirect(url_for('operator.client_detail', client_id=client_id))


@operator_bp.route('/clients/<int:client_id>/rates/<int:rate_id>/update', methods=['POST'])
@login_required
@_require_operator
def client_rate_update(client_id, rate_id):
    from db_utils import get_repo
    rate_repo = get_repo('client_rate')
    data = {
        'fee_name': request.form.get('fee_name', '').strip(),
        'fee_type': request.form.get('fee_type', 'fixed'),
        'amount': request.form.get('amount', 0, type=float),
        'unit_label': request.form.get('unit_label', '건').strip(),
        'category': request.form.get('category', 'custom').strip(),
        'memo': request.form.get('memo', '').strip(),
    }
    rate_repo.update_rate(rate_id, data)
    flash('요금 항목이 수정되었습니다.', 'success')
    return redirect(url_for('operator.client_detail', client_id=client_id))


@operator_bp.route('/clients/<int:client_id>/rates/<int:rate_id>/delete', methods=['POST'])
@login_required
@_require_operator
def client_rate_delete(client_id, rate_id):
    from db_utils import get_repo
    rate_repo = get_repo('client_rate')
    rate_repo.delete_rate(rate_id)
    flash('요금 항목이 삭제되었습니다.', 'success')
    return redirect(url_for('operator.client_detail', client_id=client_id))


# ═══ 고객사 과금 프리셋 ═══

@operator_bp.route('/clients/<int:client_id>/rates/preset', methods=['POST'])
@login_required
@_require_operator
def client_rate_preset(client_id):
    """프리셋 항목 일괄 추가."""
    from db_utils import get_repo
    from services.client_billing_service import RATE_PRESETS
    rate_repo = get_repo('client_rate')
    categories = request.form.getlist('categories')
    if not categories:
        flash('카테고리를 선택해주세요.', 'warning')
        return redirect(url_for('operator.client_detail', client_id=client_id))

    count = rate_repo.count_rates(client_id)
    existing = rate_repo.list_rates(client_id) or []
    existing_names = {r.get('fee_name') for r in existing}
    added = 0

    for preset in RATE_PRESETS:
        if preset['category'] not in categories:
            continue
        if preset['fee_name'] in existing_names:
            continue
        if count + added >= 50:
            break
        rate_repo.create_rate({
            'client_id': client_id,
            'fee_name': preset['fee_name'],
            'fee_type': preset['fee_type'],
            'amount': preset['amount'],
            'unit_label': preset['unit_label'],
            'category': preset['category'],
            'sort_order': count + added,
        })
        added += 1

    flash(f'프리셋 {added}개 항목 추가 완료', 'success')
    return redirect(url_for('operator.client_detail', client_id=client_id))


# ═══ 고객사 과금 내역/정산 ═══

@operator_bp.route('/clients/<int:client_id>/billing')
@login_required
@_require_operator
def client_billing(client_id):
    """고객사 월별 과금 내역."""
    from db_utils import get_repo
    from services.client_billing_service import CATEGORY_LABELS
    client_repo = get_repo('client')
    client = client_repo.get_client(client_id)
    if not client:
        flash('고객사를 찾을 수 없습니다.', 'warning')
        return redirect(url_for('operator.clients'))

    billing_repo = get_repo('client_billing')
    year_month = request.args.get('month')
    if not year_month:
        from datetime import datetime, timezone
        year_month = datetime.now(timezone.utc).strftime('%Y-%m')

    summary = billing_repo.get_monthly_summary(client_id, year_month)
    invoice = billing_repo.get_invoice(client_id, year_month)

    return render_template('operator/client_billing.html',
                           client=client, year_month=year_month,
                           summary=summary, invoice=invoice,
                           category_labels=CATEGORY_LABELS)


@operator_bp.route('/clients/<int:client_id>/billing/confirm', methods=['POST'])
@login_required
@_require_operator
def client_billing_confirm(client_id):
    """정산서 확정."""
    from db_utils import get_repo
    from datetime import datetime, timezone
    billing_repo = get_repo('client_billing')
    year_month = request.form.get('year_month')
    summary = billing_repo.get_monthly_summary(client_id, year_month)

    invoice = billing_repo.get_invoice(client_id, year_month)
    if invoice:
        billing_repo.update_invoice(invoice['id'], {
            'total_amount': summary['total'],
            'status': 'confirmed',
            'confirmed_at': datetime.now(timezone.utc).isoformat(),
        })
    else:
        billing_repo.create_invoice({
            'client_id': client_id,
            'year_month': year_month,
            'total_amount': summary['total'],
            'status': 'confirmed',
            'confirmed_at': datetime.now(timezone.utc).isoformat(),
        })

    flash(f'{year_month} 정산서 확정 완료 ({summary["total"]:,.0f}원)', 'success')
    return redirect(url_for('operator.client_billing', client_id=client_id,
                            month=year_month))


# ═══ 고객사 상품 (SKU) ═══

@operator_bp.route('/clients/<int:client_id>/skus', methods=['POST'])
@login_required
@_require_operator
def client_sku_create(client_id):
    """고객사 상품 등록."""
    from db_utils import get_repo
    repo = get_repo('inventory')
    barcode = request.form.get('barcode', '').strip()
    if not barcode:
        flash('바코드는 필수 항목입니다.', 'warning')
        return redirect(url_for('operator.client_detail', client_id=client_id))
    data = {
        'sku_code': request.form.get('sku_code', '').strip(),
        'barcode': barcode,
        'name': request.form.get('name', '').strip(),
        'client_id': client_id,
        'category': request.form.get('category', '').strip(),
        'unit': request.form.get('unit', 'EA').strip(),
        'storage_temp': request.form.get('storage_temp', 'ambient'),
        'weight_g': request.form.get('weight_g', type=float),
        'memo': request.form.get('memo', '').strip(),
    }
    repo.create_sku(data)
    flash(f'상품 "{data["name"]}" 등록 완료', 'success')
    return redirect(url_for('operator.client_detail', client_id=client_id))


@operator_bp.route('/clients/<int:client_id>/skus/<int:sku_id>/update', methods=['POST'])
@login_required
@_require_operator
def client_sku_update(client_id, sku_id):
    """고객사 상품 수정."""
    from db_utils import get_repo
    repo = get_repo('inventory')
    data = {
        'sku_code': request.form.get('sku_code', '').strip(),
        'barcode': request.form.get('barcode', '').strip(),
        'name': request.form.get('name', '').strip(),
        'category': request.form.get('category', '').strip(),
        'unit': request.form.get('unit', 'EA').strip(),
        'storage_temp': request.form.get('storage_temp', 'ambient'),
        'weight_g': request.form.get('weight_g', type=float),
        'memo': request.form.get('memo', '').strip(),
    }
    repo.update_sku(sku_id, data)
    flash('상품 정보가 수정되었습니다.', 'success')
    return redirect(url_for('operator.client_detail', client_id=client_id))


# ═══ 고객사 마켓플레이스 API ═══

@operator_bp.route('/clients/<int:client_id>/marketplace', methods=['POST'])
@login_required
@_require_operator
def client_marketplace_create(client_id):
    """마켓플레이스 API 인증정보 등록."""
    from db_utils import get_repo
    repo = get_repo('client_marketplace')
    channel = request.form.get('channel', '').strip()
    if not channel:
        flash('채널을 선택해주세요.', 'warning')
        return redirect(url_for('operator.client_detail', client_id=client_id))

    data = {
        'client_id': client_id,
        'channel': channel,
        'api_client_id': request.form.get('api_client_id', '').strip(),
        'api_client_secret': request.form.get('api_client_secret', '').strip(),
        'is_active': True,
    }
    extra = {}
    vendor_id = request.form.get('vendor_id', '').strip()
    mall_id = request.form.get('mall_id', '').strip()
    if vendor_id:
        extra['vendor_id'] = vendor_id
    if mall_id:
        extra['mall_id'] = mall_id
    if extra:
        import json
        data['extra_config'] = json.dumps(extra)

    repo.create_credential(data)
    channel_names = {'naver': '네이버', 'coupang': '쿠팡', 'cafe24': '카페24'}
    flash(f'{channel_names.get(channel, channel)} API 등록 완료', 'success')
    return redirect(url_for('operator.client_detail', client_id=client_id))


@operator_bp.route('/clients/<int:client_id>/marketplace/<int:cred_id>/update', methods=['POST'])
@login_required
@_require_operator
def client_marketplace_update(client_id, cred_id):
    """마켓플레이스 API 인증정보 수정."""
    from db_utils import get_repo
    repo = get_repo('client_marketplace')
    data = {
        'api_client_id': request.form.get('api_client_id', '').strip(),
        'api_client_secret': request.form.get('api_client_secret', '').strip(),
        'is_active': request.form.get('is_active') == 'on',
    }
    extra = {}
    vendor_id = request.form.get('vendor_id', '').strip()
    mall_id = request.form.get('mall_id', '').strip()
    if vendor_id:
        extra['vendor_id'] = vendor_id
    if mall_id:
        extra['mall_id'] = mall_id
    if extra:
        import json
        data['extra_config'] = json.dumps(extra)

    repo.update_credential(cred_id, data)
    flash('API 정보가 수정되었습니다.', 'success')
    return redirect(url_for('operator.client_detail', client_id=client_id))


@operator_bp.route('/clients/<int:client_id>/marketplace/<int:cred_id>/delete', methods=['POST'])
@login_required
@_require_operator
def client_marketplace_delete(client_id, cred_id):
    """마켓플레이스 API 인증정보 삭제."""
    from db_utils import get_repo
    repo = get_repo('client_marketplace')
    repo.delete_credential(cred_id)
    flash('API 연동이 삭제되었습니다.', 'success')
    return redirect(url_for('operator.client_detail', client_id=client_id))
