"""REST API v1 — 외부 연동용."""
from flask import Blueprint, jsonify, request

api_bp = Blueprint('api', __name__)


@api_bp.route('/health')
def health():
    return jsonify({'status': 'ok'})


@api_bp.route('/orders', methods=['POST'])
def create_order():
    """외부 쇼핑몰 → 주문 자동 등록 API."""
    # TODO: API key 인증 + 주문 생성
    data = request.json
    return jsonify({'status': 'received', 'order_id': None}), 201


@api_bp.route('/inventory/<sku_code>')
def check_inventory(sku_code):
    """실시간 재고 조회 API."""
    # TODO: SKU 코드로 재고 조회
    return jsonify({'sku_code': sku_code, 'available': 0})
