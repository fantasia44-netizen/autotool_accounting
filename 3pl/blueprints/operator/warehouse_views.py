"""창고/존/로케이션 관련 라우트."""
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required

from . import operator_bp, _require_operator


# ═══ 창고관리 ═══

@operator_bp.route('/warehouses')
@login_required
@_require_operator
def warehouses():
    from db_utils import get_repo
    repo = get_repo('warehouse')
    items = repo.list_warehouses()
    return render_template('operator/warehouses.html', warehouses=items)


@operator_bp.route('/warehouses/new', methods=['POST'])
@login_required
@_require_operator
def warehouse_create():
    """창고 생성."""
    from db_utils import get_repo
    repo = get_repo('warehouse')
    data = {
        'name': request.form.get('name', '').strip(),
        'address': request.form.get('address', '').strip(),
        'storage_type': request.form.get('storage_type', 'ambient'),
        'memo': request.form.get('memo', '').strip(),
        'is_active': True,
    }
    if not data['name']:
        flash('창고명을 입력해주세요.', 'warning')
        return redirect(url_for('operator.warehouses'))
    repo.create_warehouse(data)
    flash(f'창고 "{data["name"]}" 등록 완료', 'success')
    return redirect(url_for('operator.warehouses'))


@operator_bp.route('/warehouses/<int:wh_id>')
@login_required
@_require_operator
def warehouse_detail(wh_id):
    from db_utils import get_repo
    repo = get_repo('warehouse')
    wh = repo.get_warehouse(wh_id)
    if not wh:
        flash('창고를 찾을 수 없습니다.', 'warning')
        return redirect(url_for('operator.warehouses'))
    zones = repo.list_zones(wh_id)
    for zone in zones:
        zone['locations'] = repo.list_locations(zone['id'])
    return render_template('operator/warehouse_detail.html', warehouse=wh, zones=zones)


@operator_bp.route('/warehouses/<int:wh_id>/update', methods=['POST'])
@login_required
@_require_operator
def warehouse_update(wh_id):
    """창고 정보 수정."""
    from db_utils import get_repo
    repo = get_repo('warehouse')
    data = {
        'name': request.form.get('name', '').strip(),
        'address': request.form.get('address', '').strip(),
        'storage_type': request.form.get('storage_type', 'ambient'),
        'memo': request.form.get('memo', '').strip(),
    }
    repo.update_warehouse(wh_id, data)
    flash('창고 정보가 수정되었습니다.', 'success')
    return redirect(url_for('operator.warehouse_detail', wh_id=wh_id))


@operator_bp.route('/warehouses/<int:wh_id>/zones', methods=['POST'])
@login_required
@_require_operator
def zone_create(wh_id):
    """구역 추가."""
    from db_utils import get_repo
    repo = get_repo('warehouse')
    data = {
        'warehouse_id': wh_id,
        'name': request.form.get('name', '').strip(),
        'storage_temp': request.form.get('storage_temp', 'ambient'),
        'memo': request.form.get('memo', '').strip(),
    }
    if not data['name']:
        flash('구역명을 입력해주세요.', 'warning')
        return redirect(url_for('operator.warehouse_detail', wh_id=wh_id))
    repo.create_zone(data)
    flash(f'구역 "{data["name"]}" 추가 완료', 'success')
    return redirect(url_for('operator.warehouse_detail', wh_id=wh_id))


@operator_bp.route('/warehouses/<int:wh_id>/locations', methods=['POST'])
@login_required
@_require_operator
def location_create(wh_id):
    """로케이션 추가."""
    from db_utils import get_repo
    repo = get_repo('warehouse')
    zone_id = request.form.get('zone_id', type=int)
    data = {
        'zone_id': zone_id,
        'code': request.form.get('code', '').strip(),
        'location_type': request.form.get('location_type', 'shelf'),
        'memo': request.form.get('memo', '').strip(),
    }
    if not data['code']:
        flash('로케이션 코드를 입력해주세요.', 'warning')
        return redirect(url_for('operator.warehouse_detail', wh_id=wh_id))
    repo.create_location(data)
    flash(f'로케이션 "{data["code"]}" 추가 완료', 'success')
    return redirect(url_for('operator.warehouse_detail', wh_id=wh_id))
