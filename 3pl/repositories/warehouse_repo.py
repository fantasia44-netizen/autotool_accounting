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
                           order_by='name', order_desc=False)

    def create_zone(self, data):
        return self._insert(self.ZONE_TABLE, data)

    # ── 로케이션 ──

    def list_locations(self, zone_id):
        return self._query(self.LOCATION_TABLE,
                           filters=[('zone_id', 'eq', zone_id)],
                           order_by='code', order_desc=False)

    def create_location(self, data):
        return self._insert(self.LOCATION_TABLE, data)

    def list_all_locations(self):
        """전체 로케이션 목록 (zone 무관)."""
        return self.client.table(self.LOCATION_TABLE).select('*').execute().data or []
