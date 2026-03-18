"""REST API v1 — 외부 연동용.

현재 인증 미구현 상태이므로 health 외 엔드포인트는 비활성화.
상용화 시 API Key 인증 구현 후 활성화 예정.
"""
from flask import Blueprint, jsonify, request

api_bp = Blueprint('api', __name__)


@api_bp.route('/health')
def health():
    return jsonify({'status': 'ok'})


@api_bp.route('/orders', methods=['POST'])
def create_order():
    """외부 쇼핑몰 → 주문 자동 등록 API.

    NOTE: 인증 미구현 — 상용화 전 API Key 인증 필수.
    """
    return jsonify({
        'error': 'API 인증이 구현되지 않았습니다. 관리자에게 문의하세요.',
        'status': 'disabled',
    }), 403


@api_bp.route('/inventory/<sku_code>')
def check_inventory(sku_code):
    """실시간 재고 조회 API.

    NOTE: 인증 미구현 — 상용화 전 API Key 인증 필수.
    """
    return jsonify({
        'error': 'API 인증이 구현되지 않았습니다. 관리자에게 문의하세요.',
        'status': 'disabled',
    }), 403
