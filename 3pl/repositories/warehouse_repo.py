"""창고 관리 Repository."""
from .base import BaseRepository


class WarehouseRepository(BaseRepository):
    """창고, 구역, 로케이션 관리."""

    TABLE = 'warehouses'
    ZONE_TABLE = 'warehouse_zones'
    LOCATION_TABLE = 'warehouse_locations'

    # ── 창고 ──

    def list_warehouses(self):
        return self._query(self.TABLE, order_by='name', order_desc=False)

    def get_warehouse(self, warehouse_id):
        rows = self._query(self.TABLE, filters=[('id', 'eq', warehouse_id)])
        return rows[0] if rows else None

    def create_warehouse(self, data):
        return self._insert(self.TABLE, data)

    def update_warehouse(self, warehouse_id, data):
        return self._update(self.TABLE, warehouse_id, data)

    # ── 구역 ──

    def list_zones(self, warehouse_id):
        return self._query(self.ZONE_TABLE,
                           filters=[('warehouse_id', 'eq', warehouse_id)],
                           order_by='name', order_desc=False,
                           skip_tenant=True)

    def create_zone(self, data):
        return self._insert(self.ZONE_TABLE, data)

    # ── 로케이션 ──

    def list_locations(self, zone_id):
        return self._query(self.LOCATION_TABLE,
                           filters=[('zone_id', 'eq', zone_id),
                                    ('is_active', 'eq', True)],
                           order_by='code', order_desc=False,
                           skip_tenant=True)

    def create_location(self, data):
        return self._insert(self.LOCATION_TABLE, data)

    def update_location(self, location_id, data):
        """로케이션 수정 (부모 FK로 테넌트 격리)."""
        return self._update(self.LOCATION_TABLE, location_id, data)

    def list_all_locations(self):
        """전체 로케이션 목록 (zone 무관, 활성만, 테넌트 내 창고만)."""
        # 1) 현재 테넌트의 창고 ID 조회
        warehouses = self.list_warehouses()
        if not warehouses:
            return []
        wh_ids = [w['id'] for w in warehouses]
        # 2) 해당 창고의 zone ID 조회
        zone_rows = self.client.table(self.ZONE_TABLE).select('id').in_(
            'warehouse_id', wh_ids).execute().data or []
        if not zone_rows:
            return []
        zone_ids = [z['id'] for z in zone_rows]
        # 3) 해당 zone의 활성 로케이션만 반환
        return self.client.table(self.LOCATION_TABLE).select(
            '*').in_('zone_id', zone_ids).eq('is_active', True
        ).execute().data or []

    def list_all_locations_with_path(self):
        """전체 로케이션 + 창고/구역 이름 포함.

        Returns: [{ id, code, zone_id, zone_name, warehouse_id, warehouse_name, storage_temp }, ...]
        """
        locations = self.list_all_locations()
        if not locations:
            return []

        # zone 정보 일괄 조회
        zone_ids = list({loc.get('zone_id') for loc in locations if loc.get('zone_id')})
        zones = {}
        if zone_ids:
            rows = self.client.table(self.ZONE_TABLE).select('*').in_('id', zone_ids).execute().data or []
            zones = {z['id']: z for z in rows}

        # warehouse 정보 일괄 조회
        wh_ids = list({z.get('warehouse_id') for z in zones.values() if z.get('warehouse_id')})
        warehouses = {}
        if wh_ids:
            rows = self.client.table(self.TABLE).select('*').in_('id', wh_ids).execute().data or []
            warehouses = {w['id']: w for w in rows}

        result = []
        for loc in locations:
            zone = zones.get(loc.get('zone_id'), {})
            wh = warehouses.get(zone.get('warehouse_id'), {})
            result.append({
                **loc,
                'zone_name': zone.get('name', ''),
                'storage_temp': zone.get('storage_temp', 'ambient'),
                'warehouse_id': zone.get('warehouse_id'),
                'warehouse_name': wh.get('name', ''),
                'display': f"{wh.get('name', '?')} > {zone.get('name', '?')} > {loc.get('code', '?')}",
            })
        return result

    def get_location(self, location_id):
        """로케이션 단건 조회 (skip_tenant: 자식 테이블)."""
        rows = self._query(self.LOCATION_TABLE,
                           filters=[('id', 'eq', location_id)],
                           skip_tenant=True)
        return rows[0] if rows else None
