"""REST API v1 — 외부 연동용.

API Key 인증 기반. 관리자 > 설정에서 API Key 발급.
Header: X-API-Key: <key>
"""
import functools
import hashlib
import hmac
import logging
from flask import Blueprint, jsonify, request, g

api_bp = Blueprint('api', __name__)
logger = logging.getLogger(__name__)


def _require_api_key(f):
    """API Key 인증 데코레이터.

    X-API-Key 헤더의 키를 api_keys 테이블에서 조회.
    유효하면 g.api_client_id, g.operator_id 설정.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        api_key = request.headers.get('X-API-Key', '').strip()
        if not api_key:
            return jsonify({
                'error': 'API Key가 필요합니다.',
                'hint': 'X-API-Key 헤더에 발급받은 키를 포함하세요.',
            }), 401

        # api_keys 테이블 조회
        try:
            from db_utils import get_supabase
            sb = get_supabase()
            # 키 해시로 비교 (평문 저장 대신 해시 저장 권장)
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            res = sb.table('api_keys').select('*') \
                .eq('key_hash', key_hash) \
                .eq('is_active', True) \
                .execute()

            if not res.data:
                # fallback: 평문 비교 (마이그레이션 전 호환)
                res = sb.table('api_keys').select('*') \
                    .eq('api_key', api_key) \
                    .eq('is_active', True) \
                    .execute()

            if not res.data:
                logger.warning('API 인증 실패: 잘못된 키 시도')
                return jsonify({'error': '유효하지 않은 API Key입니다.'}), 401

            key_record = res.data[0]
            g.api_client_id = key_record.get('client_id')
            g.operator_id = key_record.get('operator_id')
            g.api_key_id = key_record.get('id')

            # 마지막 사용 시각 업데이트 (비동기적으로, 실패해도 무시)
            try:
                from datetime import datetime, timezone
                sb.table('api_keys').update({
                    'last_used_at': datetime.now(timezone.utc).isoformat(),
                }).eq('id', key_record['id']).execute()
            except Exception:
                pass

        except Exception as e:
            # api_keys 테이블이 없으면 API 비활성 상태
            logger.error('API Key 인증 실패: %s', e)
            return jsonify({
                'error': 'API 인증 시스템이 설정되지 않았습니다.',
                'status': 'disabled',
            }), 503

        return f(*args, **kwargs)
    return wrapper


# ═══ 엔드포인트 ═══

@api_bp.route('/health')
def health():
    return jsonify({'status': 'ok'})


@api_bp.route('/orders', methods=['POST'])
@_require_api_key
def create_order():
    """외부 쇼핑몰 → 주문 자동 등록 API."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON body 필요'}), 400

    required = ['recipient_name', 'recipient_phone', 'recipient_address']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'error': f'필수 필드 누락: {", ".join(missing)}'}), 400

    try:
        from db_utils import get_repo
        order_repo = get_repo('order')

        order_data = {
            'client_id': g.api_client_id,
            'channel': data.get('channel', 'api'),
            'channel_order_id': data.get('channel_order_id', ''),
            'recipient_name': data['recipient_name'],
            'recipient_phone': data['recipient_phone'],
            'recipient_address': data['recipient_address'],
            'recipient_zipcode': data.get('recipient_zipcode', ''),
            'delivery_message': data.get('delivery_message', ''),
            'status': 'pending',
        }
        order = order_repo.create_order(order_data)

        # 주문 아이템
        items = data.get('items', [])
        for item in items:
            order_repo.create_order_item({
                'order_id': order['id'],
                'sku_id': item.get('sku_id'),
                'sku_code': item.get('sku_code', ''),
                'quantity': item.get('quantity', 1),
            })

        return jsonify({
            'status': 'created',
            'order_id': order['id'],
        }), 201

    except Exception as e:
        logger.exception('API 주문 생성 실패')
        return jsonify({'error': f'주문 생성 실패: {e}'}), 500


@api_bp.route('/inventory/<sku_code>')
@_require_api_key
def check_inventory(sku_code):
    """실시간 재고 조회 API."""
    try:
        from db_utils import get_repo
        inv_repo = get_repo('inventory')

        # SKU 조회
        skus = inv_repo.list_skus(client_id=g.api_client_id) or []
        sku = next((s for s in skus if s.get('sku_code') == sku_code), None)
        if not sku:
            return jsonify({'error': f'SKU 코드 미등록: {sku_code}'}), 404

        # 재고 조회
        stocks = inv_repo.list_stock(sku_id=sku['id']) or []
        total_qty = sum(s.get('quantity', 0) for s in stocks)

        return jsonify({
            'sku_code': sku_code,
            'sku_name': sku.get('name', ''),
            'total_quantity': total_qty,
            'locations': [
                {
                    'location': s.get('location_code', ''),
                    'quantity': s.get('quantity', 0),
                    'lot_number': s.get('lot_number', ''),
                }
                for s in stocks if s.get('quantity', 0) > 0
            ],
        })

    except Exception as e:
        logger.exception('API 재고 조회 실패: sku_code=%s', sku_code)
        return jsonify({'error': f'재고 조회 실패: {e}'}), 500
