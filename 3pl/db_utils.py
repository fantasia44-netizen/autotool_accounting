"""Thread-safe repository access helper."""
from flask import g, current_app


class DemoProxy:
    """Supabase 없을 때 빈 데이터 반환하는 프록시.

    모든 메서드 호출에 대해 빈 리스트/딕트/0 반환.
    로컬 테스트에서 페이지 렌더링이 깨지지 않도록.
    """
    # 리스트를 반환해야 하는 메서드 패턴
    _LIST_METHODS = {'list_', 'search_', 'get_recent_', 'get_low_stock',
                     'get_expiring_', 'get_pending_', 'get_worker_'}

    # 데모 고객사 데이터
    _DEMO_CLIENTS = [
        {'id': 1, 'name': '(주)스마트커머스', 'business_no': '123-45-67890',
         'contact_name': '김담당', 'contact_phone': '010-1234-5678',
         'contact_email': 'kim@smartcommerce.kr', 'address': '서울시 강남구',
         'memo': '데모 고객사', 'is_active': True},
        {'id': 2, 'name': '패션브랜드 A', 'business_no': '234-56-78901',
         'contact_name': '이매니저', 'contact_phone': '010-2345-6789',
         'contact_email': '', 'address': '경기도 성남시',
         'memo': '', 'is_active': True},
    ]

    # 데모 피킹리스트
    _DEMO_PICKING_LISTS = [
        {'id': 1, 'list_no': 'PL-20260315-001', 'list_type': 'by_order',
         'warehouse_id': None, 'client_id': None, 'status': 'created',
         'assigned_to': None, 'total_items': 3, 'picked_items': 0,
         'created_by': None, 'created_at': '2026-03-15T09:00:00Z',
         'completed_at': None},
    ]

    _DEMO_PICKING_ITEMS = [
        {'id': 1, 'picking_list_id': 1, 'order_id': 1, 'sku_id': 1,
         'location_id': 1, 'location_code': 'A-01-01', 'expected_qty': 5,
         'picked_qty': 0, 'lot_number': 'LOT001', 'status': 'pending'},
        {'id': 2, 'picking_list_id': 1, 'order_id': 1, 'sku_id': 2,
         'location_id': 2, 'location_code': 'A-02-03', 'expected_qty': 3,
         'picked_qty': 0, 'lot_number': None, 'status': 'pending'},
        {'id': 3, 'picking_list_id': 1, 'order_id': 2, 'sku_id': 1,
         'location_id': 1, 'location_code': 'A-01-01', 'expected_qty': 2,
         'picked_qty': 0, 'lot_number': 'LOT001', 'status': 'pending'},
    ]

    def __getattr__(self, name):
        def method(*args, **kwargs):
            # count 계열
            if name == 'count_rates':
                return 0
            if name == 'count_by_status':
                return {'created': 1, 'in_progress': 0, 'completed': 0}
            if name.startswith('count'):
                return {}
            # 데모 고객사 목록
            if name == 'list_clients':
                return DemoProxy._DEMO_CLIENTS
            # 데모 고객사 단건
            if name == 'get_client':
                client_id = args[0] if args else None
                for c in DemoProxy._DEMO_CLIENTS:
                    if c['id'] == client_id:
                        return c
                return None
            # 피킹리스트 데모
            if name == 'list_picking_lists':
                status = kwargs.get('status') or (args[0] if args else None)
                if status:
                    return [p for p in DemoProxy._DEMO_PICKING_LISTS
                            if p['status'] == status]
                return list(DemoProxy._DEMO_PICKING_LISTS)
            if name == 'get_picking_list_with_items':
                list_id = args[0] if args else None
                for pl in DemoProxy._DEMO_PICKING_LISTS:
                    if pl['id'] == list_id:
                        result = dict(pl)
                        result['items'] = [
                            i for i in DemoProxy._DEMO_PICKING_ITEMS
                            if i['picking_list_id'] == list_id
                        ]
                        return result
                return None
            if name == 'update_item_picked':
                return True
            if name == 'complete_picking_list':
                return True
            # 주문 상태 로그
            if name == 'get_status_logs':
                return []
            if name == 'log_status_change':
                return None
            if name == 'hold_order' or name == 'release_hold':
                return True
            # 과금 요약
            if name == 'get_monthly_summary':
                return {'by_category': {}, 'total': 0, 'items': []}
            # 경영분석 P&L
            if name == 'get_pnl':
                return {'revenue': 0, 'cost_of_service': 0, 'operating_expense': 0,
                        'gross_profit': 0, 'net_income': 0, 'detail': {}, 'year_month': ''}
            if name == 'sum_expenses_by_month':
                return {'by_category': {}, 'total': 0, 'items': []}
            # 리스트 반환 패턴 체크
            for prefix in DemoProxy._LIST_METHODS:
                if name.startswith(prefix):
                    return []
            # get_/create_/update_ 계열은 None (단건)
            if name.startswith(('get_', 'create_', 'update_',
                                'approve_', 'deactivate_', 'delete_')):
                return None
            # 기본: 빈 리스트
            return []
        return method


def get_repo(name):
    """현재 요청의 operator_id로 repository 인스턴스 반환.

    Supabase 미연결 시 DemoProxy로 대체 (페이지 렌더링만 가능).
    """
    repo_class = current_app.repos.get(name)
    if not repo_class:
        raise ValueError(f"Unknown repository: {name}")

    if not current_app.supabase:
        return DemoProxy()

    return repo_class(current_app.supabase, g.get('operator_id'))
