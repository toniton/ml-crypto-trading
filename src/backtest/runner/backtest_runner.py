from __future__ import annotations

from dataclasses import replace
from queue import Queue
from typing import Mapping, Optional

from api.interfaces.asset import Asset
from api.interfaces.backtest_request import BacktestRequest, ExecutionConfiguration
from src.backtest.backtest_clock import BacktestClock
from src.backtest.backtest_engine import BacktestEngine
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.backtest_infrastructure import BacktestInfrastructure
from src.backtest.backtest_result_collector import BacktestResultCollector
from src.backtest.backtest_rest_service import BacktestRestService
from src.backtest.backtest_trading_scheduler import BacktestTradingScheduler
from src.backtest.backtest_websocket_service import BacktestWebSocketService
from src.backtest.data.backtest_data_set import BacktestDataSet
from src.backtest.data.backtest_data_source_resolver import BacktestDataSourceResolver
from src.backtest.domain.result import BacktestResult
from src.backtest.domain.session import BacktestSession
from src.backtest.execution.backtest_execution_engine import BacktestExecutionEngine
from src.backtest.execution.execution_model import ExecutionModel
from src.backtest.execution.fees.percentage_fee import PercentageFee
from src.backtest.execution.latency.fixed_latency import FixedLatencyModel
from src.backtest.execution.slippage.fixed_tick_slippage import FixedTickSlippage
from src.configuration.strategies_config import StrategiesConfig
from src.database.database_manager import DatabaseManager
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
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
            data_source_resolver: Optional[BacktestDataSourceResolver] = None,
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
        self._resolver = data_source_resolver or BacktestDataSourceResolver()

    def run(self, requests: list[BacktestRequest]) -> list[BacktestResult]:
        if not requests:
            return []

        assets = [self._resolve_asset(request.ticker_symbol) for request in requests]
        engine, bus = self._build_engine(requests, assets)

        results = []
        for asset, request in zip(assets, requests):
            session = BacktestSession(ticker_symbol=request.ticker_symbol, request=request)
            results.append(self._run_session(session, asset, engine, bus))
        return results

    def run_one(self, request: BacktestRequest) -> BacktestResult:
        return self.run_session(BacktestSession(ticker_symbol=request.ticker_symbol, request=request))

    def run_session(self, session: BacktestSession) -> BacktestResult:
        asset = self._resolve_asset(session.request.ticker_symbol)
        engine, bus = self._build_engine([session.request], [asset])
        return self._run_session(session, asset, engine, bus)

    def _build_engine(self, requests, assets):  # pylint: disable=too-many-locals
        first = requests[0]
        datasets = self._load_datasets(requests, assets)
        timestamps = {symbol: list(dataset.timestamps) for symbol, dataset in datasets.items()}
        clock = BacktestClock(timestamps, tick_delay=0.0)
        bus = BacktestEventBus()
        execution_engine = BacktestExecutionEngine(
            clock=clock,
            datasets=datasets,
            bus=bus,
            execution_model=build_execution_model(first.execution),
            assets={asset.ticker_symbol: asset for asset in assets},
            initial_balance=first.initial_balance,
        )

        managers, _ = ManagerFactory.build_manager_container(self._db_manager, assets, is_backtest=True)
        managers.rest_manager.register_service(BacktestRestService(clock, bus, datasets, execution_engine))
        managers.websocket_manager.register_service(BacktestWebSocketService(bus))

        scheduler = BacktestTradingScheduler(clock)
        executor = TradingExecutor(
            assets, managers, self._activity_queue, self._dynamic_quantity,
            strategies_registry=self._strategy_registry,
        )
        infrastructure = BacktestInfrastructure(
            clock=clock, datasets=datasets, bus=bus, execution_engine=execution_engine
        )
        engine = BacktestEngine(scheduler, executor, infrastructure=infrastructure, assets=assets)

        engine.start_application()
        return engine, bus

    @staticmethod
    def _run_session(
            session: BacktestSession,
            asset: Asset,
            engine: BacktestEngine,
            bus: BacktestEventBus,
    ) -> BacktestResult:
        collector = BacktestResultCollector(bus)
        session.start()
        try:
            engine.run([asset])
            result = collector.build_result(session)
        except Exception as exc:  # pylint: disable=broad-except
            session.fail(str(exc))
            raise
        session.complete(result)
        return result

    def _resolve_asset(self, ticker_symbol: str) -> Asset:
        asset = self._assets.get(ticker_symbol)
        if asset is None:
            raise ValueError(
                f"Asset '{ticker_symbol}' not found. Available: {sorted(self._assets)}"
            )
        return self._as_backtest_asset(asset)

    @staticmethod
    def _as_backtest_asset(asset: Asset) -> Asset:
        # The backtest services register under the BACKTEST provider; normalize the
        # asset's exchange so live configs (e.g. CRYPTO_DOT_COM) route through them.
        if asset.exchange == ExchangeProvidersEnum.BACKTEST:
            return asset
        return replace(asset, exchange=ExchangeProvidersEnum.BACKTEST)

    def _load_datasets(
            self,
            requests: list[BacktestRequest],
            assets: list[Asset],
    ) -> dict[str, BacktestDataSet]:
        datasets: dict[str, BacktestDataSet] = {}
        for asset, request in zip(assets, requests):
            source = self._resolver.resolve(request.data_source)
            datasets[asset.ticker_symbol] = source.load(request)
        return datasets
