from __future__ import annotations

from typing import Optional

from api.interfaces.asset import Asset
from src.backtest.backtest_infrastructure import BacktestInfrastructure
from src.backtest.backtest_simulator import BacktestSimulator
from src.core.interfaces.trading_scheduler import TradingScheduler
from src.trading.trading_engine import TradingEngine
from src.trading.trading_executor import TradingExecutor
from src.trading.trading_oracle import TradingOracle


class BacktestEngine(TradingEngine):
    def __init__(
            self,
            trading_scheduler: TradingScheduler,
            trading_executor: Optional[TradingExecutor] = None,
            oracle_scheduler: Optional[TradingScheduler] = None,
            trading_oracle: Optional[TradingOracle] = None,
            infrastructure: Optional[BacktestInfrastructure] = None,
            assets: Optional[list[Asset]] = None,
    ):
        super().__init__(trading_scheduler, trading_executor, oracle_scheduler, trading_oracle)
        self._assets = assets or []
        self._simulator = None
        if infrastructure is not None:
            self._simulator = BacktestSimulator(
                clock=infrastructure.clock,
                loader=infrastructure.loader,
                execution_engine=infrastructure.execution_engine,
                bus=infrastructure.bus,
                strategy=self._trigger_trading_cycle,
            )

    def _trigger_trading_cycle(self, asset: Asset, timestamp: int, market_data, candles) -> None:  # pylint: disable=unused-argument
        self._trading_scheduler.on_tick(timestamp, asset)

    def _run_trading_cycle(self, assets: list[Asset]) -> None:
        # The backtest is synchronous and deterministic; run the trading cycle
        # inline instead of dispatching to the live bot's thread pool.
        self._trading_executor.create_buy_order(assets)
        self._trading_executor.create_sell_order(assets)

    def _start_oracle_cycle(self):
        pass

    def _stop_oracle_cycle(self):
        pass

    def start_application(self):
        if self._trading_executor is not None:
            super().start_application()

    def run(self, assets: Optional[list[Asset]] = None) -> None:
        if self._simulator is not None:
            self._simulator.run(assets if assets is not None else self._assets)

    def stop(self) -> None:
        if self._simulator is not None:
            self._simulator.stop()
