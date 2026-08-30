from __future__ import annotations

from queue import Queue
from typing import Mapping, Optional

from api.interfaces.asset import Asset
from api.interfaces.backtest_request import BacktestRequest, ExecutionConfiguration
from src.backtest.backtest_clock import BacktestClock
from src.backtest.backtest_data_loader import BacktestDataLoader
from src.backtest.backtest_engine import BacktestEngine
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.backtest_infrastructure import BacktestInfrastructure
from src.backtest.backtest_result_collector import BacktestResultCollector
from src.backtest.backtest_rest_service import BacktestRestService
from src.backtest.backtest_trading_scheduler import BacktestTradingScheduler
from src.backtest.backtest_websocket_service import BacktestWebSocketService
from src.backtest.domain.result import BacktestResult
from src.backtest.domain.session import BacktestSession
from src.backtest.execution.backtest_execution_engine import BacktestExecutionEngine
from src.backtest.execution.execution_model import ExecutionModel
from src.backtest.execution.fees.percentage_fee import PercentageFee
from src.backtest.execution.latency.fixed_latency import FixedLatencyModel
from src.backtest.execution.slippage.fixed_tick_slippage import FixedTickSlippage
from src.configuration.strategies_config import StrategiesConfig
from src.database.database_manager import DatabaseManager
from src.trading.managers.manager_factory import ManagerFactory
from src.trading.strategies.strategy_registry import StrategyRegistry
from src.trading.trading_executor import TradingExecutor


def build_execution_model(config: ExecutionConfiguration) -> ExecutionModel:
    return ExecutionModel(
        latency=FixedLatencyModel(config.latency_ms),
        slippage=FixedTickSlippage(config.slippage_ticks),
        fees=PercentageFee(config.fee_rate),
    )


class BacktestRunner:
    def __init__(
            self,
            db_manager: DatabaseManager,
            assets: Mapping[str, Asset],
            strategy_registry: Optional[StrategyRegistry] = None,
            activity_queue: Optional[Queue] = None,
            dynamic_quantity: Optional[str] = None,
    ):
        self._db_manager = db_manager
        self._assets = assets
        self._strategy_registry = (
            strategy_registry
            if strategy_registry is not None
            else StrategyRegistry(StrategiesConfig().strategies)
        )
        self._activity_queue = activity_queue or Queue()
        self._dynamic_quantity = dynamic_quantity

    def run(self, requests: list[BacktestRequest]) -> list[BacktestResult]:
        if not requests:
            return []

        first = requests[0]
        assets = [self._resolve_asset(request.asset) for request in requests]

        loader = BacktestDataLoader(first.market_data.data_source)
        timestamps = {}
        for asset, request in zip(assets, requests):
            timestamps[asset.ticker_symbol] = self._load_timestamps(loader, asset, request)
        clock = BacktestClock(timestamps, tick_delay=0.0)
        bus = BacktestEventBus()
        execution_engine = BacktestExecutionEngine(
            clock=clock,
            loader=loader,
            bus=bus,
            execution_model=build_execution_model(first.execution),
            assets={asset.ticker_symbol: asset for asset in assets},
            initial_balance=first.initial_balance,
        )

        managers, _ = ManagerFactory.build_manager_container(self._db_manager, assets, is_backtest=True)
        managers.rest_manager.register_service(BacktestRestService(clock, bus, loader, execution_engine))
        managers.websocket_manager.register_service(BacktestWebSocketService(bus))

        scheduler = BacktestTradingScheduler(clock)
        executor = TradingExecutor(
            assets, managers, self._activity_queue, self._dynamic_quantity,
            strategies_registry=self._strategy_registry,
        )
        infrastructure = BacktestInfrastructure(
            clock=clock, loader=loader, bus=bus, execution_engine=execution_engine
        )
        engine = BacktestEngine(scheduler, executor, infrastructure=infrastructure, assets=assets)

        engine.start_application()

        results = []
        for asset, request in zip(assets, requests):
            session = BacktestSession(asset=request.asset, request=request)
            collector = BacktestResultCollector(bus)
            session.start()
            engine.run([asset])
            result = collector.build_result(session)
            session.complete(result)
            results.append(result)
        return results

    def run_one(self, request: BacktestRequest) -> BacktestResult:
        return self.run([request])[0]

    def _resolve_asset(self, ticker_symbol: str) -> Asset:
        asset = self._assets.get(ticker_symbol)
        if asset is None:
            raise ValueError(
                f"Asset '{ticker_symbol}' not found. Available: {sorted(self._assets)}"
            )
        return asset

    @staticmethod
    def _load_timestamps(
            loader: BacktestDataLoader,
            asset: Asset,
            request,
    ) -> list[int]:
        all_points = loader.load(asset.ticker_symbol)
        start_epoch = int(request.start_time.timestamp())
        end_epoch = int(request.end_time.timestamp())
        return [dp.timestamp for dp in all_points if start_epoch <= dp.timestamp <= end_epoch]
