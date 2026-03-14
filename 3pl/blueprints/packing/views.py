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
