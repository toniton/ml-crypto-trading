from typing import Callable, List

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from backtest.backtest_clock import BacktestClock
from src.core.interfaces.trading_scheduler import TradingScheduler


class BacktestTradingScheduler(TradingScheduler):
    def __init__(self, clock: 'BacktestClock'):
        super().__init__()
        self._clock = clock
        self._callback: Callable[[List[Asset]], None] = None

    def start(self, callback: Callable[[List[Asset]], None]):
        """
        No threads, no loops.
        Scheduler is advanced by the backtest engine.
        """
        self._callback = callback

    def on_tick(self, timestamp: int):
        if not self._callback:
            return

        for schedule in self.get_registered_schedules():
            if self._should_run(schedule, timestamp):
                callback_assets = self.get_assets(schedule)
                self._callback(callback_assets)

    def stop(self):
        pass

    def _should_run(self, schedule: AssetSchedule, timestamp: int) -> bool:
        interval = self.UNIT_SECONDS[schedule]
        return timestamp % interval == 0
