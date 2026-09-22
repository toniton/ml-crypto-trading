from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, List

from api.interfaces.asset import Asset
from src.trading.scheduling.asset_schedule_registry import AssetScheduleRegistry


class TradingScheduler(AssetScheduleRegistry, ABC):
    @abstractmethod
    def start(self, callback: Callable[[List[Asset]], None]):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def update_schedules(
            self,
            assets: List[Asset],
            callback: Callable[[List[Asset]], None] | None = None,
    ) -> None:
        pass
