from abc import ABC

from schedule import every

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule


class AssetScheduleRegistry(ABC):
    UNIT_MAP = {
        AssetSchedule.EVERY_SECOND: lambda: every(1).second,
        AssetSchedule.EVERY_MINUTE: lambda: every(1).minute,
        AssetSchedule.EVERY_HOUR: lambda: every(1).hour,
        AssetSchedule.EVERY_DAY: lambda: every(1).day,
    }
    UNIT_SECONDS = {
        AssetSchedule.EVERY_SECOND: 1,
        AssetSchedule.EVERY_MINUTE: 60,
        AssetSchedule.EVERY_HOUR: 3600,
        AssetSchedule.EVERY_DAY: 86400,
        AssetSchedule.EVERY_WEEK: 86400 * 7,
    }

    def __init__(self):
        self.schedules: dict[AssetSchedule, list[Asset]] = {}

    def register_assets(self, assets: list[Asset]):
        for asset in assets:
            asset_schedule = asset.schedule
            if asset_schedule not in self.schedules:
                self.schedules[asset_schedule] = []
            if asset in self.schedules[asset_schedule]:
                raise ValueError(f"Asset {asset.name} already registered.")
            self.schedules[asset_schedule].append(asset)

    def get_assets(self, schedule: AssetSchedule) -> list[Asset]:
        assets = self.schedules.get(schedule)
        if assets is None:
            raise ValueError(f"Schedule {schedule} not registered.")
        return assets

    def get_registered_schedules(self) -> list[AssetSchedule]:
        return list(self.schedules.keys())
