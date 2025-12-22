from __future__ import annotations

from threading import Event

from src.trading.trading_executor import TradingExecutor
from src.trading.trading_scheduler import TradingScheduler


class TradingEngine:
    def __init__(
            self,
            trading_scheduler: TradingScheduler,
            trading_executor: TradingExecutor
    ):
        self._trading_scheduler = trading_scheduler
        self._trading_executor = trading_executor
        self._is_running = Event()

    def start_application(self):
        self._trading_executor.init_application()
        self._trading_scheduler.start(self._trading_executor.create_buy_order)
        self._trading_scheduler.start(self._trading_executor.check_unclosed_orders)
        self._is_running.set()

    def stop_application(self):
        # FIXME: Consider cancelling all pending/open trades as part of application shutdown procedures.
        if self._is_running.is_set():
            self._trading_scheduler.stop()
            self._trading_executor.print_context()
        self._is_running.clear()
