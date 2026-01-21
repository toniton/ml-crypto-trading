from abc import ABC, abstractmethod
from typing import Callable, List

from api.interfaces.asset import Asset
from src.core.registries.asset_schedule_registry import AssetScheduleRegistry


class TradingScheduler(AssetScheduleRegistry, ABC):
    @abstractmethod
    def start(self, callback: Callable[[List[Asset]], None]):
        pass

    @abstractmethod
    def stop(self):
        pass
