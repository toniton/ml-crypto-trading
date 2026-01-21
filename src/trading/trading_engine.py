from __future__ import annotations

from threading import Event

from api.interfaces.asset import Asset
from src.trading.trading_executor import TradingExecutor
from src.core.interfaces.trading_scheduler import TradingScheduler


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
        self._is_running.set()
        self._trading_executor.init_application()

        def run_trading_cycle(assets: list[Asset]) -> None:
            self._trading_executor.create_buy_order(assets)
            self._trading_executor.create_sell_order(assets)

        self._trading_scheduler.start(run_trading_cycle)

    def stop_application(self):
        if self._is_running.is_set():
            self._trading_scheduler.stop()
            self._trading_executor.stop()
        self._is_running.clear()
