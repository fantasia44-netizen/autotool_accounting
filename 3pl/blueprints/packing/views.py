"""패킹센터 포털 — 작업큐, 바코드스캔, 촬영모드, 실적."""
import json
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from functools import wraps

packing_bp = Blueprint('packing', __name__)


def _require_packing(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_packing():
            from flask import abort
            abort(403)
        return f(*args, **kwargs)
    return decorated


@packing_bp.route('/dashboard')
@login_required
@_require_packing
def dashboard():
    from db_utils import get_repo
    repo = get_repo('packing')
    active_jobs = repo.list_jobs(status='recording') or []
    completed = repo.get_worker_stats(current_user.id) or []
    return render_template('packing/dashboard.html',
                           active_jobs=active_jobs,
                           completed_count=len(completed))


@packing_bp.route('/queue')
@login_required
@_require_packing
def queue():
    from db_utils import get_repo
    repo = get_repo('packing')
    pending = repo.get_pending_queue() or []
    return render_template('packing/queue.html', jobs=pending)


@packing_bp.route('/scan', methods=['GET', 'POST'])
@login_required
@_require_packing
def scan():
    from db_utils import get_repo

    if request.method == 'POST':
        data = request.get_json(silent=True)
        if data:
            barcode = data.get('barcode', '')
            inv_repo = get_repo('inventory')
            sku = inv_repo.get_sku_by_barcode(barcode)
            if sku:
                return jsonify({'status': 'ok', 'sku': sku})
            return jsonify({'status': 'not_found', 'barcode': barcode}), 404

    return render_template('packing/scan.html')


@packing_bp.route('/stats')
@login_required
@_require_packing
def stats():
    from db_utils import get_repo
    repo = get_repo('packing')
    my_jobs = repo.get_worker_stats(current_user.id) or []
    all_jobs = repo.list_jobs(status='completed') or []
    return render_template('packing/stats.html', my_jobs=my_jobs, all_jobs=all_jobs)


# ═══════════════════════════════════════════════════
# 피킹모드 (Picking Mode)
# ═══════════════════════════════════════════════════

@packing_bp.route('/picking')
@login_required
@_require_packing
def picking():
    """피킹모드 — 작업자 전용."""
    from db_utils import get_repo
    repo = get_repo('picking')
    # 진행 가능한 피킹리스트 (created/in_progress)
    lists = []
    for status in ('created', 'in_progress'):
        lists.extend(repo.list_picking_lists(status=status) or [])
    return render_template('packing/picking.html', lists=lists)


@packing_bp.route('/api/picking/<int:list_id>/items')
@login_required
@_require_packing
def api_picking_items(list_id):
    """피킹리스트 항목 API (JSON)."""
    from db_utils import get_repo
    repo = get_repo('picking')
    inv_repo = get_repo('inventory')

    pl = repo.get_picking_list_with_items(list_id)
    if not pl:
        return jsonify({'ok': False, 'error': '피킹리스트 없음'})

    # 상태를 in_progress로 전환
    if pl.get('status') == 'created':
        repo.update_picking_list(list_id, {'status': 'in_progress'})

    # SKU 정보 보강
    items = []
    for it in pl.get('items', []):
        sku = inv_repo.get_sku(it.get('sku_id')) if it.get('sku_id') else None
        items.append({
            'id': it['id'],
            'location_code': it.get('location_code', '-'),
            'sku_name': sku.get('name', '') if sku else '',
            'sku_code': sku.get('sku_code', '') if sku else '',
            'barcode': sku.get('barcode', '') if sku else '',
            'expected_qty': it.get('expected_qty', 0),
            'picked_qty': it.get('picked_qty', 0),
            'lot_number': it.get('lot_number', ''),
            'status': it.get('status', 'pending'),
        })

    return jsonify({
        'ok': True,
        'list_no': pl.get('list_no', ''),
        'total_items': len(items),
        'items': items,
    })


@packing_bp.route('/api/picking/confirm-pick', methods=['POST'])
@login_required
@_require_packing
def api_picking_confirm():
    """피킹 항목 스캔 확인."""
    data = request.get_json(silent=True) or {}
    item_id = data.get('item_id')
    picked_qty = data.get('picked_qty', 0)

    if not item_id:
        return jsonify({'ok': False, 'error': 'item_id 누락'})

    from db_utils import get_repo
    repo = get_repo('picking')
    repo.update_item_picked(item_id, picked_qty)
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════
# 촬영모드 (Recording Mode)
# ═══════════════════════════════════════════════════

@packing_bp.route('/recording')
@login_required
@_require_packing
def recording():
    """촬영모드 페이지."""
    return render_template('packing/recording.html')


@packing_bp.route('/api/lookup-barcode', methods=['POST'])
@login_required
@_require_packing
def api_lookup_barcode():
    """송장번호(바코드)로 주문 검색."""
    data = request.get_json(silent=True) or {}
    barcode = data.get('barcode', '').strip()
    if not barcode:
        return jsonify({'ok': False, 'error': '바코드를 입력해주세요.'})

    from db_utils import get_repo
    order_repo = get_repo('order')

    # 송장번호로 출고 조회
    barcode_clean = barcode.replace('-', '')
    shipments = order_repo.search_by_invoice(barcode_clean) or []

    if not shipments:
        return jsonify({'ok': False,
                        'error': f'송장번호 "{barcode}"에 해당하는 주문이 없습니다.'})

    ship = shipments[0]
    channel = ship.get('channel', '')
    order_no = ship.get('order_no', '')
    order_id = ship.get('order_id')

    # ── 출고 차단 검증 (Phase 1) ──
    if order_id:
        from services.shipment_guard import validate_order_for_shipping
        guard = validate_order_for_shipping(order_repo, order_id)
        if guard.get('blocked'):
            return jsonify({
                'ok': False,
                'blocked': True,
                'block_type': guard.get('block_type', 'unknown'),
                'error': guard.get('reason', '출고할 수 없는 주문입니다.'),
            })

    # 주문 상세 (items)
    order = order_repo.get_order_with_items(order_id) if order_id else None
    items = []
    order_items_raw = []  # 스캔 검증용 원본 아이템
    if order and order.get('items'):
        for it in order['items']:
            items.append({
                'sku_id': it.get('sku_id'),
                'product_name': it.get('sku_name', it.get('product_name', '')),
                'qty': abs(it.get('quantity', it.get('qty', 0))),
                'option_name': it.get('option_name', ''),
                'barcode': it.get('barcode', ''),
            })
            order_items_raw.append({
                'sku_id': it.get('sku_id'),
                'quantity': abs(it.get('quantity', it.get('qty', 0))),
            })

    # 수취인 마스킹
    name = ship.get('recipient_name', ship.get('name', ''))
    if name and len(name) > 1:
        masked = name[0] + '*' * (len(name) - 1)
    else:
        masked = '***'

    product_summary = ', '.join(
        f"{it['product_name']} x{it['qty']}" for it in items[:5]
    ) if items else '(품목 없음)'
    if len(items) > 5:
        product_summary += f' 외 {len(items) - 5}건'

    return jsonify({
        'ok': True,
        'data': {
            'channel': channel,
            'order_no': order_no,
            'order_id': order_id,
            'recipient_name': masked,
            'courier': ship.get('courier', ''),
            'items': items,
            'order_items': order_items_raw,
            'product_summary': product_summary,
            'total_qty': sum(it['qty'] for it in items),
        }
    })


@packing_bp.route('/api/start-job', methods=['POST'])
@login_required
@_require_packing
def api_start_job():
    """녹화 시작 — packing_jobs 레코드 생성."""
    data = request.get_json(silent=True) or {}
    barcode = data.get('barcode', '').strip()
    if not barcode:
        return jsonify({'ok': False, 'error': '바코드 없음'})

    from db_utils import get_repo

    # ── 작업 시작 직전 주문 상태 재검증 ──
    order_id = data.get('order_id')
    if order_id:
        order_repo = get_repo('order')
        from services.shipment_guard import validate_order_for_shipping
        guard = validate_order_for_shipping(order_repo, order_id)
        if guard.get('blocked'):
            return jsonify({
                'ok': False,
                'blocked': True,
                'block_type': guard.get('block_type', 'unknown'),
                'error': guard.get('reason', '출고할 수 없는 주문입니다.'),
            })

    repo = get_repo('packing')

    job = {
        'user_id': current_user.id,
        'scanned_barcode': barcode,
        'channel': data.get('channel', ''),
        'order_no': data.get('order_no', ''),
        'order_id': data.get('order_id'),
        'product_name': data.get('product_summary', ''),
        'recipient_name': data.get('recipient_name', ''),
        'order_info': json.dumps({
            'items': data.get('items', []),
        }, ensure_ascii=False),
        'status': 'recording',
        'started_at': datetime.now(timezone.utc).isoformat(),
    }

    result = repo.create_job(job)
    if not result:
        return jsonify({'ok': False, 'error': '작업 생성 실패'})

    job_id = result.get('id') if isinstance(result, dict) else result
    return jsonify({'ok': True, 'job_id': job_id})


@packing_bp.route('/api/complete-job', methods=['POST'])
@login_required
@_require_packing
def api_complete_job():
    """녹화 완료 — 영상 업로드 + 상태 갱신."""
    job_id = request.form.get('job_id')
    video_file = request.files.get('video')
    duration_ms = request.form.get('duration_ms', 0, type=int)
    scanned_items_raw = request.form.get('scanned_items', '')

    if not job_id or not video_file:
        return jsonify({'ok': False, 'error': '필수 데이터 누락'})
    # 영상 MIME 검증
    allowed_video = ('video/webm', 'video/mp4', 'video/ogg', 'video/quicktime')
    if video_file.content_type not in allowed_video:
        return jsonify({'ok': False, 'error': f'허용되지 않는 파일 형식: {video_file.content_type}'})

    from db_utils import get_repo
    repo = get_repo('packing')
    job = repo.get_job(int(job_id))
    if not job:
        return jsonify({'ok': False, 'error': '작업을 찾을 수 없습니다.'})

    # 권한 확인
    if job.get('user_id') != current_user.id:
        return jsonify({'ok': False, 'error': '권한 없음'})

    # 영상 읽기
    video_bytes = video_file.read()
    max_size = current_app.config.get('PACKING_VIDEO_MAX_BYTES', 100 * 1024 * 1024)
    if len(video_bytes) > max_size:
        return jsonify({'ok': False, 'error': f'영상 크기 초과 ({len(video_bytes) // 1024 // 1024}MB)'})

    # Storage 업로드
    now = datetime.now(timezone.utc)
    path = (f"packing/{now.strftime('%Y/%m/%d')}/"
            f"{current_user.id}_{job.get('scanned_barcode', '')}_{int(now.timestamp())}.webm")

    try:
        repo.upload_video(path, video_bytes)
    except Exception as e:
        return jsonify({'ok': False, 'error': f'영상 업로드 실패: {e}'})

    # scanned_items 파싱
    scanned_items = None
    if scanned_items_raw:
        try:
            scanned_items = json.loads(scanned_items_raw)
        except Exception:
            pass

    update_data = {
        'status': 'completed',
        'video_path': path,
        'video_size_bytes': len(video_bytes),
        'video_duration_ms': duration_ms,
        'completed_at': now.isoformat(),
    }
    if scanned_items is not None:
        existing_info = job.get('order_info') or {}
        if isinstance(existing_info, str):
            try:
                existing_info = json.loads(existing_info)
            except Exception:
                existing_info = {}
        if isinstance(existing_info, list):
            existing_info = {'items': existing_info}
        existing_info['scanned_items'] = scanned_items
        update_data['order_info'] = json.dumps(existing_info, ensure_ascii=False)

    repo.update_job(int(job_id), update_data)

    # 재고 확정 (예약 → 실차감)
    order_id = job.get('order_id')
    if order_id:
        try:
            inv_repo = get_repo('inventory')
            from services.inventory_service import commit_stock
            commit_stock(inv_repo, order_id)
        except Exception:
            pass  # 예약 없는 경우 무시

    # ── 부자재비 과금 ──
    materials_raw = request.form.get('materials', '')
    if materials_raw:
        try:
            materials = json.loads(materials_raw)
            if materials and order_id:
                order_repo = get_repo('order')
                order = order_repo.get_order(order_id)
                client_id = order.get('client_id') if order else None
                if client_id:
                    from services.client_billing_service import record_packing_fee
                    record_packing_fee(
                        get_repo('client_billing'), get_repo('client_rate'),
                        client_id, order_id=order_id, materials=materials)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('부자재비 과금 실패: job_id=%s', job_id)

    return jsonify({'ok': True})


@packing_bp.route('/api/complete-job-no-video', methods=['POST'])
@login_required
@_require_packing
def api_complete_job_no_video():
    """영상 없이 작업 완료 (카메라 없는 검증 모드)."""
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    if not job_id:
        return jsonify({'ok': False, 'error': 'job_id 누락'})

    from db_utils import get_repo
    repo = get_repo('packing')
    job = repo.get_job(int(job_id))
    if not job:
        return jsonify({'ok': False, 'error': '작업을 찾을 수 없습니다.'})

    if job.get('user_id') != current_user.id:
        return jsonify({'ok': False, 'error': '권한 없음'})

    duration_ms = data.get('duration_ms', 0)
    scanned_items = data.get('scanned_items')

    now = datetime.now(timezone.utc)
    update_data = {
        'status': 'completed',
        'video_path': None,
        'video_size_bytes': 0,
        'video_duration_ms': duration_ms,
        'completed_at': now.isoformat(),
    }
    if scanned_items is not None:
        existing_info = job.get('order_info') or {}
        if isinstance(existing_info, str):
            try:
                existing_info = json.loads(existing_info)
            except Exception:
                existing_info = {}
        if isinstance(existing_info, list):
            existing_info = {'items': existing_info}
        existing_info['scanned_items'] = scanned_items
        update_data['order_info'] = json.dumps(existing_info, ensure_ascii=False)

    repo.update_job(int(job_id), update_data)

    # 재고 확정 (예약 → 실차감)
    order_id = job.get('order_id')
    if order_id:
        try:
            inv_repo = get_repo('inventory')
            from services.inventory_service import commit_stock
            commit_stock(inv_repo, order_id)
        except Exception:
            pass  # 예약 없는 경우 무시

    # ── 부자재비 과금 ──
    materials = data.get('materials')
    if materials and order_id:
        try:
            order_repo = get_repo('order')
            order = order_repo.get_order(order_id)
            client_id = order.get('client_id') if order else None
            if client_id:
                from services.client_billing_service import record_packing_fee
                record_packing_fee(
                    get_repo('client_billing'), get_repo('client_rate'),
                    client_id, order_id=order_id, materials=materials)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('부자재비 과금 실패: job_id=%s', job_id)

    return jsonify({'ok': True})


@packing_bp.route('/api/validate-product-scan', methods=['POST'])
@login_required
@_require_packing
def api_validate_product_scan():
    """상품 바코드 스캔 검증 — 오출고 방지."""
    data = request.get_json(silent=True) or {}
    scanned_barcode = data.get('barcode', '').strip()
    order_items = data.get('order_items', [])
    already_scanned = data.get('already_scanned', {})

    if not scanned_barcode:
        return jsonify({'ok': False, 'error': '바코드를 입력해주세요.'})

    from db_utils import get_repo
    inv_repo = get_repo('inventory')

    from services.scan_validator import validate_scanned_item
    result = validate_scanned_item(inv_repo, order_items, scanned_barcode,
                                   already_scanned)

    if result.get('valid'):
        sku = result.get('sku', {})
        return jsonify({
            'ok': True,
            'sku_id': result['sku_id'],
            'sku_name': sku.get('name', ''),
            'sku_code': sku.get('sku_code', ''),
            'expected_qty': result['expected_qty'],
            'scanned_qty': result['scanned_qty'],
            'remaining': result['remaining'],
        })
    else:
        return jsonify({
            'ok': False,
            'error': result.get('error', '검증 실패'),
            'error_type': result.get('error_type', 'unknown'),
        })


@packing_bp.route('/api/cancel-job', methods=['POST'])
@login_required
@_require_packing
def api_cancel_job():
    """녹화 취소."""
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    if not job_id:
        return jsonify({'ok': False, 'error': 'job_id 누락'})

    from db_utils import get_repo
    repo = get_repo('packing')
    repo.update_job(int(job_id), {'status': 'cancelled'})
    return jsonify({'ok': True})


@packing_bp.route('/api/video-url/<int:job_id>')
@login_required
@_require_packing
def api_video_url(job_id):
    """영상 서명 URL 반환."""
    from db_utils import get_repo
    repo = get_repo('packing')
    job = repo.get_job(job_id)
    if not job:
        return jsonify({'ok': False, 'error': '작업 없음'})

    if job.get('user_id') != current_user.id:
        return jsonify({'ok': False, 'error': '권한 없음'})

    if not job.get('video_path'):
        return jsonify({'ok': False, 'error': '영상 없음'})

    url = repo.get_video_url(job['video_path'])
    if not url:
        return jsonify({'ok': False, 'error': '서명 URL 생성 실패'})

    return jsonify({'ok': True, 'url': url})


# ═══════════════════════════════════════════════════════════
# 현장모드 (Field Mode) — 입고스캔, 창고이동, 재고실사, 상차스캔
# ═══════════════════════════════════════════════════════════

@packing_bp.route('/field')
@login_required
@_require_packing
def field_dashboard():
    """현장모드 대시보드 — 오늘의 작업 현황."""
    from db_utils import get_repo
    inv_repo = get_repo('inventory')

    # 오늘 날짜 (KST)
    from services.tz_utils import now_kst
    today = now_kst().strftime('%Y-%m-%d')

    # 오늘 이동 이력 요약
    movements = inv_repo.list_movements(date_from=today + 'T00:00:00',
                                         limit=50) or []
    inbound_cnt = sum(1 for m in movements if m.get('movement_type') == 'inbound')
    outbound_cnt = sum(1 for m in movements if m.get('movement_type') == 'outbound')
    transfer_cnt = sum(1 for m in movements if m.get('movement_type') in ('transfer_in', 'transfer_out'))
    adjust_cnt = sum(1 for m in movements if m.get('movement_type') == 'adjust')

    return render_template('packing/field_dashboard.html',
                           today=today,
                           inbound_cnt=inbound_cnt,
                           outbound_cnt=outbound_cnt,
                           transfer_cnt=transfer_cnt // 2,  # in+out 쌍
                           adjust_cnt=adjust_cnt,
                           recent_movements=movements[:20])


@packing_bp.route('/field/inbound')
@login_required
@_require_packing
def field_inbound():
    """현장 입고 스캔 모드."""
    from db_utils import get_repo
    wh_repo = get_repo('warehouse')
    locations = wh_repo.list_all_locations_with_path()
    return render_template('packing/field_inbound.html', locations=locations)


@packing_bp.route('/api/field/inbound', methods=['POST'])
@login_required
@_require_packing
def api_field_inbound():
    """현장 입고 API — 바코드 스캔 후 입고 처리."""
    data = request.get_json(silent=True) or {}
    barcode = data.get('barcode', '').strip()
    location_id = data.get('location_id')
    quantity = data.get('quantity', 1)
    lot_number = data.get('lot_number', '').strip() or None

    if not barcode:
        return jsonify({'ok': False, 'error': '바코드를 입력해주세요.'})
    if not location_id:
        return jsonify({'ok': False, 'error': '로케이션을 선택해주세요.'})
    if not quantity or quantity < 1:
        return jsonify({'ok': False, 'error': '수량은 1 이상이어야 합니다.'})

    from db_utils import get_repo
    inv_repo = get_repo('inventory')

    # SKU 조회
    sku = inv_repo.get_sku_by_barcode(barcode)
    if not sku:
        sku = inv_repo.get_sku_by_code(barcode)
    if not sku:
        return jsonify({'ok': False, 'error': f'미등록 바코드: {barcode}',
                        'error_type': 'not_found'})

    # 입고 처리
    from services.warehouse_service import process_inbound
    try:
        process_inbound(inv_repo, sku['id'], int(location_id), int(quantity),
                        lot_number=lot_number,
                        memo=f'현장스캔 입고',
                        user_id=current_user.id)
    except Exception as e:
        return jsonify({'ok': False, 'error': f'입고 처리 실패: {e}'})

    # 현재 재고 조회
    stock = inv_repo.get_stock(sku['id'], int(location_id), lot_number)
    current_qty = stock['quantity'] if stock else quantity

    return jsonify({
        'ok': True,
        'sku_name': sku.get('name', ''),
        'sku_code': sku.get('sku_code', ''),
        'quantity': quantity,
        'current_stock': current_qty,
    })


@packing_bp.route('/field/transfer')
@login_required
@_require_packing
def field_transfer():
    """현장 창고이동 스캔 모드."""
    from db_utils import get_repo
    wh_repo = get_repo('warehouse')
    locations = wh_repo.list_all_locations_with_path()
    return render_template('packing/field_transfer.html', locations=locations)


@packing_bp.route('/api/field/transfer', methods=['POST'])
@login_required
@_require_packing
def api_field_transfer():
    """현장 창고이동 API — 출발위치→도착위치 재고 이동."""
    data = request.get_json(silent=True) or {}
    barcode = data.get('barcode', '').strip()
    from_location_id = data.get('from_location_id')
    to_location_id = data.get('to_location_id')
    quantity = data.get('quantity', 1)

    if not barcode:
        return jsonify({'ok': False, 'error': '상품 바코드를 입력해주세요.'})
    if not from_location_id or not to_location_id:
        return jsonify({'ok': False, 'error': '출발/도착 로케이션을 선택해주세요.'})
    if int(from_location_id) == int(to_location_id):
        return jsonify({'ok': False, 'error': '동일 위치로는 이동할 수 없습니다.'})
    if not quantity or quantity < 1:
        return jsonify({'ok': False, 'error': '수량은 1 이상이어야 합니다.'})

    from db_utils import get_repo
    inv_repo = get_repo('inventory')

    # SKU 조회
    sku = inv_repo.get_sku_by_barcode(barcode)
    if not sku:
        sku = inv_repo.get_sku_by_code(barcode)
    if not sku:
        return jsonify({'ok': False, 'error': f'미등록 바코드: {barcode}',
                        'error_type': 'not_found'})

    from_loc = int(from_location_id)
    to_loc = int(to_location_id)
    qty = int(quantity)

    # 재고 부족 체크는 RPC 내부에서 원자적으로 수행됨 (아래 process_transfer 호출)

    # 이동 처리 — RPC 원자적 이동 (동시접속 안전)
    try:
        from services.warehouse_service import process_transfer
        result = process_transfer(inv_repo, sku['id'], from_loc, to_loc, qty,
                                  memo='현장스캔 이동', user_id=current_user.id)
        if not result.get('ok'):
            return jsonify({'ok': False, 'error': result.get('error', '이동 처리 실패')})
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)})
    except Exception as e:
        return jsonify({'ok': False, 'error': f'이동 처리 실패: {e}'})

    return jsonify({
        'ok': True,
        'sku_name': sku.get('name', ''),
        'sku_code': sku.get('sku_code', ''),
        'quantity': qty,
    })


@packing_bp.route('/field/stockcheck')
@login_required
@_require_packing
def field_stockcheck():
    """현장 재고실사(Cycle Count) 스캔 모드."""
    from db_utils import get_repo
    wh_repo = get_repo('warehouse')
    locations = wh_repo.list_all_locations_with_path()
    return render_template('packing/field_stockcheck.html', locations=locations)


@packing_bp.route('/api/field/stock-at-location', methods=['POST'])
@login_required
@_require_packing
def api_field_stock_at_location():
    """특정 로케이션의 재고 목록 조회."""
    data = request.get_json(silent=True) or {}
    location_id = data.get('location_id')
    if not location_id:
        return jsonify({'ok': False, 'error': '로케이션을 선택해주세요.'})

    from db_utils import get_repo
    inv_repo = get_repo('inventory')
    stocks = inv_repo.list_stock(location_id=int(location_id))

    items = []
    for st in (stocks or []):
        sku = inv_repo.get_sku(st['sku_id']) if st.get('sku_id') else None
        items.append({
            'sku_id': st['sku_id'],
            'sku_code': sku.get('sku_code', '') if sku else '',
            'sku_name': sku.get('name', '') if sku else '',
            'barcode': sku.get('barcode', '') if sku else '',
            'system_qty': st.get('quantity', 0),
            'lot_number': st.get('lot_number', ''),
        })

    return jsonify({'ok': True, 'items': items})


@packing_bp.route('/api/field/stockcheck', methods=['POST'])
@login_required
@_require_packing
def api_field_stockcheck():
    """재고실사 조정 API — 실수량과 시스템 수량 차이 반영."""
    data = request.get_json(silent=True) or {}
    location_id = data.get('location_id')
    adjustments = data.get('adjustments', [])

    if not location_id:
        return jsonify({'ok': False, 'error': '로케이션을 선택해주세요.'})
    if not adjustments:
        return jsonify({'ok': False, 'error': '조정할 항목이 없습니다.'})

    from db_utils import get_repo
    inv_repo = get_repo('inventory')

    loc_id = int(location_id)
    adjusted_count = 0

    for adj in adjustments:
        sku_id = adj.get('sku_id')
        actual_qty = adj.get('actual_qty')
        system_qty = adj.get('system_qty', 0)

        if sku_id is None or actual_qty is None:
            continue

        delta = int(actual_qty) - int(system_qty)
        if delta == 0:
            continue

        # RPC 원자적 재고 조정 (동시접속 안전)
        try:
            from services.warehouse_service import _call_rpc
            result = _call_rpc(inv_repo, 'fn_adjust_stock', {
                'p_operator_id': inv_repo.operator_id,
                'p_sku_id': int(sku_id),
                'p_location_id': loc_id,
                'p_delta': delta,
                'p_memo': f'현장실사: 시스템 {system_qty} → 실제 {actual_qty}',
                'p_user_id': current_user.id,
            })
            if result.get('ok'):
                adjusted_count += 1
        except Exception:
            pass  # 개별 항목 실패는 스킵

    return jsonify({'ok': True, 'adjusted_count': adjusted_count})


@packing_bp.route('/field/shipping')
@login_required
@_require_packing
def field_shipping():
    """현장 출고상차 스캔 모드."""
    return render_template('packing/field_shipping.html')


@packing_bp.route('/api/field/shipping-scan', methods=['POST'])
@login_required
@_require_packing
def api_field_shipping_scan():
    """출고상차 송장 스캔 API — 송장번호로 주문 찾아 상차 완료 처리."""
    data = request.get_json(silent=True) or {}
    barcode = data.get('barcode', '').strip()

    if not barcode:
        return jsonify({'ok': False, 'error': '송장번호를 스캔해주세요.'})

    from db_utils import get_repo
    order_repo = get_repo('order')

    barcode_clean = barcode.replace('-', '')
    shipments = order_repo.search_by_invoice(barcode_clean) or []

    if not shipments:
        return jsonify({'ok': False, 'error': f'송장번호 "{barcode}" 미확인',
                        'error_type': 'not_found'})

    ship = shipments[0]
    order_id = ship.get('order_id')
    status = ship.get('status', '')

    # 이미 출고 완료된 건
    if status in ('shipped', 'delivered'):
        return jsonify({'ok': False,
                        'error': f'이미 출고된 송장입니다 ({status})',
                        'error_type': 'already_shipped'})

    # 상차 완료 처리 (상태 → shipped)
    try:
        if order_id:
            order_repo.update_order_status(order_id, 'shipped')
    except Exception as e:
        return jsonify({'ok': False, 'error': f'상태 변경 실패: {e}'})

    return jsonify({
        'ok': True,
        'order_no': ship.get('order_no', ''),
        'recipient': ship.get('recipient_name', ship.get('name', '')),
        'channel': ship.get('channel', ''),
        'courier': ship.get('courier', ''),
    })


@packing_bp.route('/api/field/sku-lookup', methods=['POST'])
@login_required
@_require_packing
def api_field_sku_lookup():
    """바코드로 SKU 정보 + 재고 조회 (현장모드 공통)."""
    data = request.get_json(silent=True) or {}
    barcode = data.get('barcode', '').strip()
    location_id = data.get('location_id')

    if not barcode:
        return jsonify({'ok': False, 'error': '바코드를 입력해주세요.'})

    from db_utils import get_repo
    inv_repo = get_repo('inventory')

    sku = inv_repo.get_sku_by_barcode(barcode)
    if not sku:
        sku = inv_repo.get_sku_by_code(barcode)
    if not sku:
        return jsonify({'ok': False, 'error': f'미등록 바코드: {barcode}',
                        'error_type': 'not_found'})

    result = {
        'ok': True,
        'sku_id': sku['id'],
        'sku_code': sku.get('sku_code', ''),
        'sku_name': sku.get('name', ''),
        'barcode': sku.get('barcode', ''),
        'storage_temp': sku.get('storage_temp', 'ambient'),
    }

    # 특정 위치의 재고
    if location_id:
        stock = inv_repo.get_stock(sku['id'], int(location_id))
        result['stock_qty'] = stock['quantity'] if stock else 0

    # 전체 재고
    all_stocks = inv_repo.list_stock_by_sku(sku['id'])
    result['total_stock'] = sum(s.get('quantity', 0) for s in (all_stocks or []))

    return jsonify(result)


# ═══════════════════════════════════════════════════
# 속도모드 (Speed Mode) — 1-Touch 단품 + 합포 수량확인
# ═══════════════════════════════════════════════════

@packing_bp.route('/speed')
@login_required
@_require_packing
def speed_mode():
    """속도모드 패킹 페이지."""
    return render_template('packing/speed_mode.html')


@packing_bp.route('/api/speed/lookup', methods=['POST'])
@login_required
@_require_packing
def api_speed_lookup():
    """속도모드: 송장 스캔 → 주문 조회 + 자동판별.

    단품: 즉시 완료 가능 상태 반환.
    합포: 수량 확인 필요 상태 반환.
    """
    data = request.get_json(silent=True) or {}
    barcode = data.get('barcode', '').strip()
    if not barcode:
        return jsonify({'ok': False, 'error': '바코드를 입력해주세요.'})

    from db_utils import get_repo
    order_repo = get_repo('order')

    barcode_clean = barcode.replace('-', '')
    shipments = order_repo.search_by_invoice(barcode_clean) or []

    if not shipments:
        # 송장 없으면 주문번호로 검색
        orders = order_repo.search_orders(barcode_clean) or []
        if not orders:
            return jsonify({'ok': False, 'error': f'주문을 찾을 수 없습니다: {barcode}'})
        order = orders[0]
    else:
        ship = shipments[0]
        order = order_repo.get_order(ship.get('order_id'))

    if not order:
        return jsonify({'ok': False, 'error': '주문 정보 없음'})

    order_id = order['id']
    order_full = order_repo.get_order_with_items(order_id)
    items = order_full.get('items', []) if order_full else []

    # SKU 정보 보강
    inv_repo = get_repo('inventory')
    item_details = []
    for it in items:
        sku = inv_repo.get_sku(it.get('sku_id')) if it.get('sku_id') else None
        item_details.append({
            'sku_id': it.get('sku_id'),
            'sku_name': sku.get('name', '') if sku else '',
            'barcode': sku.get('barcode', '') if sku else '',
            'qty': it.get('quantity', 1),
        })

    pack_type = order.get('pack_type', 'single')
    distinct_skus = len(set(it.get('sku_id') for it in items))
    if not pack_type:
        pack_type = 'single' if distinct_skus == 1 else 'multi'

    return jsonify({
        'ok': True,
        'order_id': order_id,
        'order_no': order.get('order_no', ''),
        'channel': order.get('channel', ''),
        'pack_type': pack_type,
        'total_items': len(items),
        'total_qty': sum(it.get('quantity', 1) for it in items),
        'items': item_details,
        'status': order.get('status', ''),
        'auto_complete': pack_type == 'single',  # 단품이면 자동 완료 가능
    })


@packing_bp.route('/api/speed/complete', methods=['POST'])
@login_required
@_require_packing
def api_speed_complete():
    """속도모드: 패킹 즉시 완료 (검수/영상 생략).

    단품: 바로 완료.
    합포: 수량 확인 후 완료.
    """
    data = request.get_json(silent=True) or {}
    order_id = data.get('order_id')
    if not order_id:
        return jsonify({'ok': False, 'error': 'order_id 누락'})

    from db_utils import get_repo
    order_repo = get_repo('order')
    order = order_repo.get_order(order_id)

    if not order:
        return jsonify({'ok': False, 'error': '주문 없음'})

    status = order.get('status', '')
    if status in ('shipped', 'delivered', 'cancelled'):
        return jsonify({'ok': False, 'error': f'이미 처리된 주문 (상태: {status})'})

    # 재고 커밋 (예약분 → 실차감)
    try:
        inv_repo = get_repo('inventory')
        from services.inventory_service import commit_stock
        commit_stock(inv_repo, order_id)
    except Exception as e:
        current_app.logger.warning(f'[속도모드] 재고커밋 실패 order_id={order_id}: {e}')

    # 주문 상태 → packed
    order_repo.update_order_status(order_id, 'packed')
    order_repo.log_status_change(order_id, status, 'packed',
                                 changed_by=current_user.id,
                                 reason='속도모드 즉시완료')

    # 과금 큐 적재 (비동기)
    try:
        client_id = order.get('client_id')
        if client_id:
            _enqueue_speed_billing(order_id, client_id, order_repo)
    except Exception as e:
        current_app.logger.warning(f'[속도모드] 과금큐 적재 실패: {e}')

    # 작업자 활동 로그
    try:
        _log_worker_activity(order_id, order)
    except Exception:
        pass

    return jsonify({'ok': True, 'message': '패킹 완료 (속도모드)'})


def _enqueue_speed_billing(order_id, client_id, order_repo):
    """속도모드 과금 이벤트를 billing_queue에 적재."""
    from db_utils import get_repo
    from flask import g
    order_full = order_repo.get_order_with_items(order_id)
    items = order_full.get('items', []) if order_full else []
    item_count = len(items)
    total_qty = sum(it.get('quantity', 1) for it in items)

    repo = get_repo('client')
    try:
        repo.supabase.table('billing_queue').insert({
            'operator_id': g.operator_id,
            'client_id': client_id,
            'event_type': 'outbound',
            'event_data': {
                'order_id': order_id,
                'item_count': item_count,
                'total_qty': total_qty,
                'mode': 'speed',
            },
        }).execute()
    except Exception as e:
        current_app.logger.error(f'[billing_queue] insert 실패: {e}')


def _log_worker_activity(order_id, order):
    """작업자 활동 로그 기록."""
    from db_utils import get_repo
    from flask import g
    repo = get_repo('client')
    items = order.get('items', [])
    try:
        repo.supabase.table('worker_activity_log').insert({
            'operator_id': g.operator_id,
            'user_id': current_user.id,
            'activity_type': 'pack',
            'fulfillment_mode': 'speed',
            'order_id': order_id,
            'item_count': len(items) if items else 1,
            'started_at': datetime.now(timezone.utc).isoformat(),
            'completed_at': datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception:
        pass
