from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from api.interfaces.asset import Asset
from src.configuration.trading_config import TradingConfig
from src.core.interfaces.trading_scheduler import TradingScheduler
from src.trading.trading_executor import TradingExecutor
from src.trading.trading_oracle import TradingOracle


class TradingEngine:
    def __init__(
            self,
            trading_scheduler: TradingScheduler,
            trading_executor: TradingExecutor,
            oracle_scheduler: TradingScheduler,
            trading_oracle: TradingOracle
    ):
        self._trading_scheduler = trading_scheduler
        self._trading_executor = trading_executor
        self._oracle_scheduler = oracle_scheduler
        self._trading_oracle = trading_oracle
        self.thread_pool_executor = ThreadPoolExecutor(max_workers=30)
        self._is_running = Event()

    def start_application(self):
        self._is_running.set()
        self._trading_executor.init_application()

        self._trading_scheduler.start(self._run_trading_cycle)
        self._start_oracle_cycle()

    def _run_trading_cycle(self, assets: list[Asset]) -> None:
        self.thread_pool_executor.submit(self._trading_executor.create_buy_order, assets)
        self.thread_pool_executor.submit(self._trading_executor.create_sell_order, assets)

    def _start_oracle_cycle(self):
        def run_oracle_cycle(assets: list[Asset]) -> None:
            self.thread_pool_executor.submit(self._trading_oracle.generate_report, assets)

        self._oracle_scheduler.start(run_oracle_cycle)

    def stop_application(self):
        if self._is_running.is_set():
            self._trading_scheduler.stop()
            self._trading_executor.stop()
            self._stop_oracle_cycle()
        self._is_running.clear()

    def _stop_oracle_cycle(self):
        self._oracle_scheduler.stop()

    def update_config(self, trading_config: TradingConfig) -> None:
        self._trading_executor.update_config(trading_config)
