from threading import Lock
from typing import Callable

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from backtest.backtest_clock import BacktestClock
from src.core.interfaces.trading_scheduler import TradingScheduler


class BacktestTradingScheduler(TradingScheduler):
    def __init__(self, clock: BacktestClock):
        super().__init__()
        self._lock = Lock()
        self._clock = clock
        self._callbacks: list[Callable[[list[Asset]], None]] = []

    def start(self, callback: Callable[[list[Asset]], None]):
        with self._lock:
            self._callbacks.append(callback)

    def on_tick(self, timestamp: int):
        with self._lock:
            if len(self._callbacks) == 0:
                return

            for schedule in self.get_registered_schedules():
                if self._should_run(schedule, timestamp):
                    callback_assets = self.get_assets(schedule)
                    for callback in self._callbacks:
                        callback(callback_assets)

    def stop(self):
        pass

    def _should_run(self, schedule: AssetSchedule, timestamp: int) -> bool:
        interval = self.UNIT_SECONDS[schedule]
        return timestamp % interval == 0
