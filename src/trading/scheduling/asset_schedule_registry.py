from __future__ import annotations

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from src.core.registry import MultiRegistry


class AssetScheduleRegistry(MultiRegistry[AssetSchedule, Asset]):
    UNIT_MAP = {
        AssetSchedule.EVERY_SECOND: lambda s: s.every(1).second,
        AssetSchedule.EVERY_MINUTE: lambda s: s.every(1).minute,
        AssetSchedule.EVERY_HOUR: lambda s: s.every(1).hour,
        AssetSchedule.EVERY_DAY: lambda s: s.every(1).day,
        AssetSchedule.EVERY_WEEK: lambda s: s.every(1).week,
        AssetSchedule.EVERY_MONTH: lambda s: s.every(4).week,
    }
    UNIT_SECONDS = {
        AssetSchedule.EVERY_SECOND: 1,
        AssetSchedule.EVERY_MINUTE: 60,
        AssetSchedule.EVERY_HOUR: 3600,
        AssetSchedule.EVERY_DAY: 86400,
        AssetSchedule.EVERY_WEEK: 86400 * 7,
        AssetSchedule.EVERY_MONTH: 86400 * 7 * 4,
    }

    def register_assets(self, assets: list[Asset], override_schedule: AssetSchedule | None = None):
        for asset in assets:
            asset_schedule = asset.schedule if override_schedule is None else override_schedule
            self.register(asset_schedule, asset)

    def get_assets(self, schedule: AssetSchedule) -> list[Asset]:
        return self.get(schedule)

    def get_registered_schedules(self) -> list[AssetSchedule]:
        return self.keys()
