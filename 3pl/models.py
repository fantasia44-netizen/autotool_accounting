"""3PL SaaS 모델 정의 — 사용자, 역할, 페이지 레지스트리, 동적 메뉴."""
from flask_login import UserMixin


# ── 역할 계층 ──
ROLES = {
    # 플랫폼
    'super_admin': {'level': 0, 'label': '플랫폼 관리자'},
    # 3PL 운영사
    'owner': {'level': 1, 'label': '대표'},
    'admin': {'level': 2, 'label': '관리자'},
    'manager': {'level': 3, 'label': '운영 책임자'},
    'warehouse': {'level': 4, 'label': '창고 관리자'},
    'cs': {'level': 5, 'label': 'CS 담당'},
    'viewer': {'level': 6, 'label': '조회 전용'},
    # 고객사
    'client_admin': {'level': 10, 'label': '고객사 관리자'},
    'client_staff': {'level': 11, 'label': '고객사 직원'},
    'client_viewer': {'level': 12, 'label': '고객사 조회'},
    # 패킹센터
    'packing_lead': {'level': 20, 'label': '패킹 리더'},
    'packing_worker': {'level': 21, 'label': '패킹 작업자'},
}

# 포털별 허용 역할
PORTAL_ROLES = {
    'operator': ['super_admin', 'owner', 'admin', 'manager', 'warehouse', 'cs', 'viewer'],
    'client': ['client_admin', 'client_staff', 'client_viewer'],
    'packing': ['packing_lead', 'packing_worker'],
}

# ═══ 페이지 레지스트리 ═══
# key = endpoint name, value = 페이지 메타
PAGE_REGISTRY = {
    # ── Operator 포털 ──
    'operator.dashboard':  {'label': '대시보드',     'icon': 'bi-speedometer2',   'portal': 'operator', 'min_role': 'viewer'},
    'operator.orders':     {'label': '주문관리',     'icon': 'bi-cart3',          'portal': 'operator', 'min_role': 'cs'},
    'operator.shipments':  {'label': '택배출고',     'icon': 'bi-truck',          'portal': 'operator', 'min_role': 'cs'},
    'operator.picking':    {'label': '피킹관리',     'icon': 'bi-clipboard-check', 'portal': 'operator', 'min_role': 'warehouse'},
    'operator.packing':    {'label': '패킹센터',     'icon': 'bi-box-seam',       'portal': 'operator', 'min_role': 'warehouse'},
    'operator.inventory':  {'label': '재고현황',     'icon': 'bi-boxes',          'portal': 'operator', 'min_role': 'viewer'},
    'operator.inbound':    {'label': '입고관리',     'icon': 'bi-box-arrow-in-down', 'portal': 'operator', 'min_role': 'warehouse'},
    'operator.returns':    {'label': '반품관리',     'icon': 'bi-arrow-return-left', 'portal': 'operator', 'min_role': 'warehouse'},
    'operator.transfers':  {'label': '창고이동',     'icon': 'bi-arrow-left-right', 'portal': 'operator', 'min_role': 'warehouse'},
    'operator.adjustment': {'label': '재고조정',     'icon': 'bi-sliders',        'portal': 'operator', 'min_role': 'manager'},
    'operator.ledger':     {'label': '이력조회',     'icon': 'bi-clock-history',  'portal': 'operator', 'min_role': 'viewer'},
    'operator.clients':    {'label': '고객사관리',   'icon': 'bi-building',       'portal': 'operator', 'min_role': 'manager'},
    'operator.warehouses': {'label': '창고관리',     'icon': 'bi-house-gear',     'portal': 'operator', 'min_role': 'warehouse'},
    'operator.skus':       {'label': '상품마스터',   'icon': 'bi-upc-scan',       'portal': 'operator', 'min_role': 'cs'},
    'operator.billing':    {'label': '과금/청구',    'icon': 'bi-receipt',        'portal': 'operator', 'min_role': 'admin'},
    'operator.billing_failed_events': {'label': '과금실패',  'icon': 'bi-exclamation-triangle', 'portal': 'operator', 'min_role': 'admin'},
    'operator.finance_dashboard':    {'label': '경영분석',  'icon': 'bi-graph-up',       'portal': 'operator', 'min_role': 'admin'},
    'operator.audit_log':            {'label': '감사로그',  'icon': 'bi-shield-check',   'portal': 'operator', 'min_role': 'admin'},
    'operator.users':      {'label': '사용자관리',   'icon': 'bi-people',         'portal': 'operator', 'min_role': 'admin'},
    # ── Client 포털 ──
    'client.dashboard':    {'label': '대시보드',     'icon': 'bi-speedometer2',   'portal': 'client', 'min_role': 'client_viewer'},
    'client.inventory':    {'label': '재고조회',     'icon': 'bi-boxes',          'portal': 'client', 'min_role': 'client_viewer'},
    'client.orders':       {'label': '주문현황',     'icon': 'bi-cart3',          'portal': 'client', 'min_role': 'client_viewer'},
    'client.videos':       {'label': '출고영상',     'icon': 'bi-camera-video',   'portal': 'client', 'min_role': 'client_viewer'},
    'client.billing':      {'label': '과금내역',     'icon': 'bi-receipt',        'portal': 'client', 'min_role': 'client_viewer'},
    # ── Packing 포털 ──
    'packing.dashboard':   {'label': '작업현황',     'icon': 'bi-speedometer2',   'portal': 'packing', 'min_role': 'packing_worker'},
    'packing.queue':       {'label': '작업큐',       'icon': 'bi-list-task',      'portal': 'packing', 'min_role': 'packing_worker'},
    'packing.scan':        {'label': '바코드스캔',   'icon': 'bi-upc-scan',       'portal': 'packing', 'min_role': 'packing_worker'},
    'packing.recording':   {'label': '촬영모드',     'icon': 'bi-camera-video-fill', 'portal': 'packing', 'min_role': 'packing_worker'},
    'packing.picking':     {'label': '피킹모드',     'icon': 'bi-clipboard-check', 'portal': 'packing', 'min_role': 'packing_worker'},
    'packing.stats':       {'label': '실적조회',     'icon': 'bi-bar-chart',      'portal': 'packing', 'min_role': 'packing_worker'},
    # ── 현장모드 ──
    'packing.field_dashboard':  {'label': '현장모드',     'icon': 'bi-phone',          'portal': 'packing', 'min_role': 'packing_worker'},
    'packing.field_inbound':    {'label': '입고스캔',     'icon': 'bi-box-arrow-in-down', 'portal': 'packing', 'min_role': 'packing_worker'},
    'packing.field_transfer':   {'label': '창고이동',     'icon': 'bi-arrow-left-right', 'portal': 'packing', 'min_role': 'packing_worker'},
    'packing.field_stockcheck': {'label': '재고실사',     'icon': 'bi-clipboard-data', 'portal': 'packing', 'min_role': 'packing_worker'},
    'packing.field_shipping':   {'label': '출고상차',     'icon': 'bi-truck',          'portal': 'packing', 'min_role': 'packing_worker'},
}

# ═══ 메뉴 그룹 (accordion) ═══
MENU_GROUPS = {
    'operator': [
        {'label': '운영',     'icon': 'bi-grid',          'items': ['operator.dashboard']},
        {'label': '주문/출고', 'icon': 'bi-send',          'items': ['operator.orders', 'operator.picking', 'operator.shipments', 'operator.packing']},
        {'label': '재고',     'icon': 'bi-archive',        'items': ['operator.inventory', 'operator.inbound', 'operator.returns', 'operator.transfers', 'operator.adjustment', 'operator.ledger']},
        {'label': '관리',     'icon': 'bi-gear',           'items': ['operator.clients', 'operator.warehouses', 'operator.skus']},
        {'label': '정산/분석', 'icon': 'bi-cash-stack',     'items': ['operator.billing', 'operator.billing_failed_events', 'operator.finance_dashboard']},
        {'label': '설정',     'icon': 'bi-sliders2',       'items': ['operator.audit_log', 'operator.users']},
    ],
    'client': [
        {'label': '내 물류',  'icon': 'bi-box',            'items': ['client.dashboard', 'client.inventory', 'client.orders', 'client.videos', 'client.billing']},
    ],
    'packing': [
        {'label': '현장모드',  'icon': 'bi-phone',          'items': ['packing.field_dashboard', 'packing.field_inbound', 'packing.field_transfer', 'packing.field_stockcheck', 'packing.field_shipping']},
        {'label': '패킹',    'icon': 'bi-box-seam',       'items': ['packing.dashboard', 'packing.picking', 'packing.recording', 'packing.queue', 'packing.scan', 'packing.stats']},
    ],
}


def get_menu_for_user(user):
    """사용자 역할에 맞는 메뉴 구조 반환."""
    portal = user.get_portal()
    groups = MENU_GROUPS.get(portal, [])
    user_role_level = ROLES.get(user.role, {}).get('level', 99)
    result = []
    for group in groups:
        visible_items = []
        for endpoint in group['items']:
            page = PAGE_REGISTRY.get(endpoint)
            if not page:
                continue
            min_level = ROLES.get(page['min_role'], {}).get('level', 0)
            if user_role_level <= min_level:
                visible_items.append({
                    'endpoint': endpoint,
                    'label': page['label'],
                    'icon': page['icon'],
                })
        if visible_items:
            result.append({
                'label': group['label'],
                'icon': group['icon'],
                'items': visible_items,
            })
    return result


class User(UserMixin):
    """Flask-Login 호환 사용자 모델."""

    def __init__(self, row: dict = None):
        if row:
            self.id = row.get('id')
            self.username = row.get('username', '')
            self.name = row.get('name', '')
            self.role = row.get('role', 'viewer')
            self.operator_id = row.get('operator_id')
            self.client_id = row.get('client_id')
            self.is_approved = row.get('is_approved', False)

    def get_portal(self):
        """사용자 역할에 따른 포털 반환."""
        for portal, roles in PORTAL_ROLES.items():
            if self.role in roles:
                return portal
        return 'operator'

    def is_operator(self):
        return self.role in PORTAL_ROLES['operator']

    def is_client(self):
        return self.role in PORTAL_ROLES['client']

    def is_packing(self):
        return self.role in PORTAL_ROLES['packing']

    def is_admin(self):
        return self.role in ('super_admin', 'owner', 'admin')

    def get_role_label(self):
        return ROLES.get(self.role, {}).get('label', self.role)
