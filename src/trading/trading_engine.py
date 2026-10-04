from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from api.interfaces.asset import Asset
from src.configuration.trading_config import TradingConfig
from src.core.interfaces.trading_scheduler import TradingScheduler
from src.core.interfaces.trading_strategy import TradingStrategy
from src.trading.health.enums import TradingHealthState
from src.trading.trading_executor import TradingExecutor


class TradingEngine:
    def __init__(
            self,
            trading_scheduler: TradingScheduler,
            trading_executor: TradingExecutor,
    ):
        self._trading_scheduler = trading_scheduler
        self._trading_executor = trading_executor
        self.thread_pool_executor = ThreadPoolExecutor(max_workers=30)
        self._is_running = Event()

    @property
    def is_running(self) -> bool:
        return self._is_running.is_set()

    @property
    def trading_executor(self) -> TradingExecutor:
        return self._trading_executor

    @property
    def monitored_assets(self) -> list[Asset]:
        if self._trading_executor is not None:
            return self._trading_executor.assets
        return []

    @property
    def strategies(self) -> list[TradingStrategy]:
        if self._trading_executor is not None:
            return self._trading_executor.strategies
        return []

    def start_application(self):
        self._is_running.set()
        if self._trading_executor is not None:
            self._trading_executor.health_monitor.set_state(TradingHealthState.SYNCING)

        self._trading_executor.init_application()

        if self._trading_executor is not None:
            self._trading_executor.health_monitor.set_state(TradingHealthState.READY)
            self._trading_executor.health_monitor.set_state(TradingHealthState.TRADING)

        self._trading_scheduler.start(self._run_trading_cycle)

    def _run_trading_cycle(self, assets: list[Asset]) -> None:
        self.thread_pool_executor.submit(self._trading_executor.create_buy_order, assets)
        self.thread_pool_executor.submit(self._trading_executor.create_sell_order, assets)

    def stop_application(self):
        if self._is_running.is_set():
            if (
                    self._trading_executor is not None
                    and self._trading_executor.health_monitor is not None
            ):
                self._trading_executor.health_monitor.set_state(TradingHealthState.STOPPING)

            if self._trading_scheduler is not None:
                self._trading_scheduler.stop()
            if self._trading_executor is not None:
                self._trading_executor.stop()

            if self._trading_executor is not None:
                self._trading_executor.health_monitor.set_state(TradingHealthState.STOPPED)
        self._is_running.clear()

    def update_config(self, trading_config: TradingConfig) -> None:
        if self._trading_executor is not None:
            self._trading_executor.update_config(trading_config)
        if self._trading_scheduler is not None:
            self._trading_scheduler.update_schedules(trading_config.assets, self._run_trading_cycle)
