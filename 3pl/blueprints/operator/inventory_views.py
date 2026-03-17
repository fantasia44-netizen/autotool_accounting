"""재고/입고/조정/수불부/SKU 관련 라우트."""
import logging
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from . import operator_bp, _require_operator

logger = logging.getLogger(__name__)


# ═══ 재고현황 ═══

@operator_bp.route('/inventory')
@login_required
@_require_operator
def inventory():
    from db_utils import get_repo
    repo = get_repo('inventory')
    client_id = request.args.get('client_id', type=int)
    search = request.args.get('search')
    stocks = repo.list_all_stock()
    skus = repo.list_skus(client_id=client_id, search=search)
    client_repo = get_repo('client')
    clients = client_repo.list_clients()
    return render_template('operator/inventory.html', stocks=stocks, skus=skus,
                           clients=clients, filter_client_id=client_id,
                           filter_search=search)


# ═══ 입고관리 ═══

@operator_bp.route('/inbound', methods=['GET', 'POST'])
@login_required
@_require_operator
def inbound():
    from db_utils import get_repo
    inv_repo = get_repo('inventory')
    wh_repo = get_repo('warehouse')

    if request.method == 'POST':
        from services.warehouse_service import process_inbound
        sku_id = request.form.get('sku_id', type=int)
        location_id = request.form.get('location_id', type=int)
        quantity = request.form.get('quantity', type=int)
        lot_number = request.form.get('lot_number', '').strip() or None
        expiry_date = request.form.get('expiry_date', '').strip() or None
        storage_temp = request.form.get('storage_temp', '').strip() or None
        memo = request.form.get('memo', '').strip()

        try:
            process_inbound(inv_repo, sku_id, location_id, quantity,
                            lot_number=lot_number, memo=memo,
                            user_id=current_user.id,
                            expiry_date=expiry_date)
            flash(f'{quantity}개 입고 완료', 'success')
            # 과금 기록 (서비스 내부에서 DLQ 처리)
            try:
                sku = inv_repo.get_sku(sku_id)
                cid = sku.get('client_id') if sku else None
                if cid:
                    from services.client_billing_service import record_inbound_fee
                    record_inbound_fee(get_repo('client_billing'),
                                       get_repo('client_rate'), cid,
                                       quantity=quantity, memo=memo)
            except Exception:
                logger.exception('과금 서비스 호출 자체 실패 (입고): sku_id=%s', sku_id)
        except Exception as e:
            flash(f'입고 오류: {e}', 'danger')
        return redirect(url_for('operator.inbound'))

    client_repo = get_repo('client')
    clients = client_repo.list_clients() or []
    skus = inv_repo.list_skus()
    locations = wh_repo.list_all_locations_with_path()
    warehouses = wh_repo.list_warehouses()
    recent = inv_repo.list_movements(movement_type='inbound', limit=20)
    sku_map = {s['id']: f"{s['sku_code']} — {s['name']}" for s in skus}
    # 로케이션 ID→표시명 맵 (최근입고에서 사용)
    loc_map = {loc['id']: loc.get('display', loc.get('code', '?')) for loc in locations}
    return render_template('operator/inbound.html', skus=skus, locations=locations,
                           warehouses=warehouses, recent_inbounds=recent,
                           clients=clients, sku_map=sku_map, loc_map=loc_map)


# ═══ API ═══

@operator_bp.route('/api/skus-by-client')
@login_required
@_require_operator
def api_skus_by_client():
    """고객사별 SKU 목록 JSON API."""
    from flask import jsonify
    from db_utils import get_repo
    client_id = request.args.get('client_id', type=int)
    if not client_id:
        return jsonify([])
    # 테넌트 격리: 요청된 client_id가 현재 운영자 소속인지 검증
    client_repo = get_repo('client')
    client = client_repo.get_client(client_id)
    if not client:
        return jsonify([])
    repo = get_repo('inventory')
    skus = repo.list_skus(client_id=client_id) or []
    return jsonify([{'id': s['id'], 'sku_code': s['sku_code'], 'name': s['name'],
                     'barcode': s.get('barcode', '')} for s in skus])


# ═══ 재고조정 ═══

@operator_bp.route('/adjustment', methods=['GET', 'POST'])
@login_required
@_require_operator
def adjustment():
    from db_utils import get_repo
    inv_repo = get_repo('inventory')

    if request.method == 'POST':
        sku_id = request.form.get('sku_id', type=int)
        location_id = request.form.get('location_id', type=int)
        delta = request.form.get('delta', type=int)
        lot_number = request.form.get('lot_number', '').strip() or None
        memo = request.form.get('memo', '').strip()

        inv_repo.adjust_stock(sku_id, location_id, delta, lot_number)
        inv_repo.log_movement({
            'sku_id': sku_id,
            'location_id': location_id,
            'movement_type': 'adjust',
            'quantity': delta,
            'lot_number': lot_number,
            'memo': memo or '재고 조정',
            'user_id': current_user.id,
        })
        flash(f'재고 조정 완료 ({delta:+d})', 'success')
        return redirect(url_for('operator.adjustment'))

    wh_repo = get_repo('warehouse')
    skus = inv_repo.list_skus()
    locations = wh_repo.list_all_locations_with_path()
    warehouses = wh_repo.list_warehouses()
    recent = inv_repo.list_movements(movement_type='adjust', limit=20)
    loc_map = {loc['id']: loc.get('display', loc.get('code', '?')) for loc in locations}
    sku_map = {s['id']: f"{s['sku_code']} — {s['name']}" for s in skus}
    return render_template('operator/adjustment.html', skus=skus, locations=locations,
                           warehouses=warehouses, recent_adjustments=recent,
                           loc_map=loc_map, sku_map=sku_map)


# ═══ 수불부 ═══

@operator_bp.route('/ledger')
@login_required
@_require_operator
def ledger():
    from db_utils import get_repo
    repo = get_repo('inventory')
    sku_id = request.args.get('sku_id', type=int)
    movement_type = request.args.get('type')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    movements = repo.list_movements(sku_id=sku_id, movement_type=movement_type,
                                    date_from=date_from, date_to=date_to)
    skus = repo.list_skus()
    wh_repo = get_repo('warehouse')
    locations = wh_repo.list_all_locations_with_path()
    loc_map = {loc['id']: loc.get('display', loc.get('code', '?')) for loc in locations}
    sku_map = {s['id']: f"{s['sku_code']} — {s['name']}" for s in skus}
    return render_template('operator/ledger.html', movements=movements, skus=skus,
                           loc_map=loc_map, sku_map=sku_map,
                           filter_sku_id=sku_id, filter_type=movement_type,
                           filter_date_from=date_from, filter_date_to=date_to)


@operator_bp.route('/inventory/export')
@login_required
@_require_operator
def inventory_export():
    """재고 현황 엑셀 다운로드."""
    import io
    from flask import send_file
    from db_utils import get_repo
    try:
        from openpyxl import Workbook
    except ImportError:
        flash('openpyxl 미설치', 'danger')
        return redirect(url_for('operator.inventory'))

    inv_repo = get_repo('inventory')
    skus = inv_repo.list_skus() or []
    stocks = inv_repo.list_all_stock() or []
    sku_stock = {}
    for st in stocks:
        sid = st.get('sku_id')
        sku_stock[sid] = sku_stock.get(sid, 0) + st.get('quantity', 0)

    wb = Workbook()
    ws = wb.active
    ws.title = '재고현황'
    ws.append(['SKU코드', '바코드', '품명', '카테고리', '보관온도', '현재고', '최소재고'])
    for s in skus:
        ws.append([
            s.get('sku_code', ''), s.get('barcode', ''), s.get('name', ''),
            s.get('category', ''), s.get('storage_temp', 'ambient'),
            sku_stock.get(s['id'], 0), s.get('min_stock_qty', 0),
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, download_name='재고현황.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@operator_bp.route('/ledger/export')
@login_required
@_require_operator
def ledger_export():
    """수불장 엑셀 다운로드."""
    import io
    from flask import send_file
    from db_utils import get_repo
    try:
        from openpyxl import Workbook
    except ImportError:
        flash('openpyxl 미설치', 'danger')
        return redirect(url_for('operator.ledger'))

    repo = get_repo('inventory')
    sku_id = request.args.get('sku_id', type=int)
    movement_type = request.args.get('type')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    movements = repo.list_movements(sku_id=sku_id, movement_type=movement_type,
                                    date_from=date_from, date_to=date_to)

    wb = Workbook()
    ws = wb.active
    ws.title = '수불장'
    ws.append(['일시', '유형', 'SKU ID', '수량', '로케이션', 'LOT', '메모'])
    for m in movements:
        ws.append([
            m.get('created_at', '')[:19] if m.get('created_at') else '',
            m.get('movement_type', ''),
            m.get('sku_id', ''),
            m.get('quantity', 0),
            m.get('location_id', ''),
            m.get('lot_number', ''),
            m.get('memo', ''),
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, download_name='수불장.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ═══ 상품마스터 (SKU) ═══

@operator_bp.route('/skus')
@login_required
@_require_operator
def skus():
    from db_utils import get_repo
    repo = get_repo('inventory')
    search = request.args.get('search')
    client_id = request.args.get('client_id', type=int)
    items = repo.list_skus(client_id=client_id, search=search)
    client_repo = get_repo('client')
    clients = client_repo.list_clients() or []
    client_map = {c['id']: c['name'] for c in clients}
    return render_template('operator/skus.html', skus=items, clients=clients,
                           client_map=client_map,
                           filter_search=search, filter_client_id=client_id)


@operator_bp.route('/skus/sample-excel')
@login_required
@_require_operator
def sku_sample_excel():
    """상품 등록 샘플 엑셀 다운로드."""
    import io
    from flask import send_file
    try:
        from openpyxl import Workbook
    except ImportError:
        flash('openpyxl 패키지가 설치되지 않았습니다.', 'danger')
        return redirect(url_for('operator.skus'))

    wb = Workbook()
    ws = wb.active
    ws.title = '상품등록'
    headers = ['sku_code(필수)', 'barcode(필수)', 'name(필수)', 'category',
               'unit(EA/BOX/PALLET/PACK/SET)', 'storage_temp(ambient/cold/frozen)',
               'weight_g', 'memo']
    ws.append(headers)
    ws.append(['SKU-001', '8801234567890', '테스트상품A', '식품', 'EA', 'ambient', 500, '샘플'])
    ws.append(['SKU-002', '8801234567891', '냉동상품B', '냉동식품', 'BOX', 'frozen', 2000, ''])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, download_name='상품등록_샘플.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@operator_bp.route('/skus/bulk-upload', methods=['POST'])
@login_required
@_require_operator
def sku_bulk_upload():
    """상품 엑셀 일괄 업로드."""
    from db_utils import get_repo
    try:
        from openpyxl import load_workbook
    except ImportError:
        flash('openpyxl 패키지가 설치되지 않았습니다.', 'danger')
        return redirect(url_for('operator.skus'))

    f = request.files.get('file')
    if not f or not f.filename.endswith(('.xlsx', '.xls')):
        flash('엑셀 파일(.xlsx)을 선택해주세요.', 'warning')
        return redirect(url_for('operator.skus'))
    # MIME 타입 검증
    allowed_mimes = (
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
        'application/octet-stream',  # 일부 브라우저
    )
    if f.content_type not in allowed_mimes:
        flash('허용되지 않는 파일 형식입니다.', 'warning')
        return redirect(url_for('operator.skus'))

    client_id = request.form.get('client_id', type=int)
    repo = get_repo('inventory')

    wb = load_workbook(f, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))

    ok, fail = 0, 0
    for row in rows:
        if not row or len(row) < 3:
            fail += 1
            continue
        sku_code = str(row[0] or '').strip()
        barcode = str(row[1] or '').strip()
        name = str(row[2] or '').strip()
        if not sku_code or not barcode or not name:
            fail += 1
            continue
        category = str(row[3] or '').strip() if len(row) > 3 else ''
        unit = str(row[4] or 'EA').strip().upper() if len(row) > 4 else 'EA'
        if unit not in ('EA', 'BOX', 'PALLET', 'PACK', 'SET'):
            unit = 'EA'
        storage_temp = str(row[5] or 'ambient').strip().lower() if len(row) > 5 else 'ambient'
        if storage_temp not in ('ambient', 'cold', 'frozen'):
            storage_temp = 'ambient'
        weight_g = None
        if len(row) > 6 and row[6]:
            try:
                weight_g = float(row[6])
            except (ValueError, TypeError):
                pass
        memo = str(row[7] or '').strip() if len(row) > 7 else ''

        data = {
            'sku_code': sku_code, 'barcode': barcode, 'name': name,
            'category': category, 'unit': unit, 'storage_temp': storage_temp,
            'weight_g': weight_g, 'memo': memo,
        }
        if client_id:
            data['client_id'] = client_id
        try:
            repo.create_sku(data)
            ok += 1
        except Exception:
            fail += 1

    flash(f'업로드 완료: 성공 {ok}건, 실패 {fail}건', 'success' if ok else 'warning')
    if client_id:
        return redirect(url_for('operator.client_detail', client_id=client_id))
    return redirect(url_for('operator.skus'))


@operator_bp.route('/skus/new', methods=['POST'])
@login_required
@_require_operator
def sku_create():
    from db_utils import get_repo
    repo = get_repo('inventory')
    barcode = request.form.get('barcode', '').strip()
    if not barcode:
        flash('바코드는 필수 항목입니다.', 'warning')
        return redirect(url_for('operator.skus'))
    data = {
        'sku_code': request.form.get('sku_code', '').strip(),
        'barcode': barcode,
        'name': request.form.get('name', '').strip(),
        'client_id': request.form.get('client_id', type=int),
        'category': request.form.get('category', '').strip(),
        'unit': request.form.get('unit', 'EA').strip(),
        'storage_temp': request.form.get('storage_temp', 'ambient'),
        'weight_g': request.form.get('weight_g', type=float),
        'memo': request.form.get('memo', '').strip(),
    }
    repo.create_sku(data)
    flash(f'상품 "{data["name"]}" 등록 완료', 'success')
    return redirect(url_for('operator.skus'))
