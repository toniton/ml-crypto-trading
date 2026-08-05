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

        def run_trading_cycle(assets: list[Asset]) -> None:
            self.thread_pool_executor.submit(self._trading_executor.create_buy_order, assets)
            self.thread_pool_executor.submit(self._trading_executor.create_sell_order, assets)

        def run_oracle_cycle(assets: list[Asset]) -> None:
            self.thread_pool_executor.submit(self._trading_oracle.generate_report, assets)

        self._trading_scheduler.start(run_trading_cycle)
        self._oracle_scheduler.start(run_oracle_cycle)

    def stop_application(self):
        if self._is_running.is_set():
            self._trading_scheduler.stop()
            self._trading_executor.stop()
            self._oracle_scheduler.stop()
        self._is_running.clear()

    def update_config(self, trading_config: TradingConfig) -> None:
        self._trading_executor.update_config(trading_config)
