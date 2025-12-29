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
        self._last_execution: dict[str, int] = {}

    def start(self, callback: Callable[[list[Asset]], None]):
        with self._lock:
            self._callbacks.append(callback)

    def on_tick(self, current_timestamp: int, asset: Asset):
        with self._lock:
            if not self._callbacks:
                return
            symbol = asset.ticker_symbol
            previous_timestamp = self._last_execution.get(symbol)
            for schedule in self.get_registered_schedules():
                if self._should_run(schedule, current_timestamp, previous_timestamp):
                    self._last_execution[symbol] = current_timestamp
                    for callback in self._callbacks:
                        callback([asset])

    def stop(self):
        self._last_execution.clear()

    def _should_run(self, schedule: AssetSchedule, current_timestamp: int, previous_timestamp: int) -> bool:
        if previous_timestamp is None:
            return True
        interval = self.UNIT_SECONDS[schedule]
        current_bucket = current_timestamp // interval
        previous_bucket = previous_timestamp // interval
        return current_bucket > previous_bucket
