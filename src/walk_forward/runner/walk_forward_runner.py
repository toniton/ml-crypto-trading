from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional

from api.interfaces.asset import Asset
from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
    ExecutionConfiguration,
)
from api.interfaces.walk_forward import (
    FoldMetricsSummary,
    WalkForwardRunSpec,
    WalkForwardSummary,
)
from src.backtest.analysis.metrics_calculator import BacktestMetricsCalculator
from src.backtest.data.backtest_data_source_resolver import BacktestDataSourceResolver
from src.backtest.domain.session import BacktestSession, BacktestSessionStatus
from src.backtest.runner.backtest_runner import BacktestRunner
from src.configuration.strategy_config import StrategyConfig
from src.core.interfaces.database_manager import DatabaseManager
from src.database.noop_database_manager import NoopDatabaseManager
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.recorder.market_data_store import MarketDataStore
from src.server.services.dataset_service import DatasetService
from src.walk_forward.analysis.aggregator import WalkForwardAggregator
from src.walk_forward.data.dataset_integrity_guard import DatasetIntegrityGuard
from src.walk_forward.generator.fold_generator import WalkForwardFoldGenerator


def _apply_weights_to_asset(asset: Asset, weights: dict[str, float]) -> Asset:
    if not asset.strategies or not weights:
        return asset
    updated_strategies: list[StrategyConfig] = []
    for s in asset.strategies:
        if s.name and s.name in weights:
            updated_strategies.append(s.model_copy(update={"weight": float(weights[s.name])}))
        else:
            updated_strategies.append(s)
    return replace(asset, strategies=updated_strategies)


def _build_equal_weight_asset(asset: Asset) -> Asset:
    if not asset.strategies:
        return asset
    updated_strategies = [s.model_copy(update={"weight": 1.0}) for s in asset.strategies]
    return replace(asset, strategies=updated_strategies)


class WalkForwardRunner(ApplicationLoggingMixin):
    def __init__(
            self,
            db_manager: DatabaseManager = NoopDatabaseManager(),
            assets: Optional[dict[str, Asset]] = None,
            dynamic_quantity: Optional[str] = None,
            data_source_resolver: Optional[BacktestDataSourceResolver] = None,
    ):
        self._db_manager = db_manager
        self._assets = assets or {}
        self._dynamic_quantity = dynamic_quantity
        self._resolver = data_source_resolver or BacktestDataSourceResolver(
            market_data_store=MarketDataStore(),
            dataset_service=DatasetService(),
        )
        self._calculator = BacktestMetricsCalculator()

    def run(
            self,
            spec: WalkForwardRunSpec,
            run_id: Optional[str] = None,
            on_fold_complete: Optional[Callable[[FoldMetricsSummary], None]] = None,
    ) -> WalkForwardSummary:
        run_identifier = run_id or f"wf_{uuid.uuid4().hex[:12]}"
        asset = self._assets.get(spec.ticker_symbol)
        if asset is None:
            raise ValueError(f"Asset '{spec.ticker_symbol}' not found in configuration.")

        # 1. Resolve dataset
        source_type_val = spec.data_source.source_type.value
        ds_type = (
            BacktestDataSourceType.MARKET_DATA
            if source_type_val in ("recorded_market_data", "market_data")
            else BacktestDataSourceType.CSV
        )
        ds_req = BacktestDataSourceRequest(
            source_type=ds_type,
            source_id=spec.data_source.dataset_id,
            path=spec.data_source.path,
        )
        source = self._resolver.resolve(ds_req)
        full_request = BacktestRequest(
            ticker_symbol=spec.ticker_symbol,
            start_time=spec.period.start_time if spec.period else None,
            end_time=spec.period.end_time if spec.period else None,
            data_source=ds_req,
            initial_balance=spec.initial_balance,
        )
        dataset = source.load(full_request)

        # 2. Data Integrity Guard
        DatasetIntegrityGuard.validate_historical_points(dataset.data_points)

        # 3. Generate Folds
        fold_gen = WalkForwardFoldGenerator(spec.windows)
        folds = fold_gen.generate_folds(dataset.timestamps)

        if not folds:
            return WalkForwardAggregator.aggregate(run_identifier, spec.ticker_symbol, [])

        fold_summaries: list[FoldMetricsSummary] = []
        exec_cfg = ExecutionConfiguration(
            latency_ms=spec.execution.latency_ms,
            slippage_ticks=spec.execution.slippage_ticks,
            fee_rate=spec.execution.fee_rate,
        )

        target_test_asset = (
            _apply_weights_to_asset(asset, spec.candidate_weights)
            if spec.candidate_weights
            else asset
        )
        equal_weight_asset = _build_equal_weight_asset(asset)

        # 4. Execute Folds sequentially with zero state leakage
        for fold in folds:
            self.app_logger.info(
                "Running walk-forward fold %d [%s to %s]",
                fold.fold_index,
                fold.train_start.isoformat(),
                fold.test_end.isoformat(),
            )

            # In-Sample (Train) run
            train_metrics = self._execute_sub_session(
                asset=asset,
                ds_req=ds_req,
                start_time=fold.train_start,
                end_time=fold.train_end,
                initial_balance=spec.initial_balance,
                exec_cfg=exec_cfg,
            )

            # Out-of-Sample (Test) run with candidate weights
            test_metrics = self._execute_sub_session(
                asset=target_test_asset,
                ds_req=ds_req,
                start_time=fold.test_start,
                end_time=fold.test_end,
                initial_balance=spec.initial_balance,
                exec_cfg=exec_cfg,
            )

            baseline_test_return: Optional[float] = None
            if spec.candidate_weights:
                baseline_metrics = self._execute_sub_session(
                    asset=asset,
                    ds_req=ds_req,
                    start_time=fold.test_start,
                    end_time=fold.test_end,
                    initial_balance=spec.initial_balance,
                    exec_cfg=exec_cfg,
                )
                baseline_test_return = float(baseline_metrics.percentage_return)

            equal_weight_metrics = self._execute_sub_session(
                asset=equal_weight_asset,
                ds_req=ds_req,
                start_time=fold.test_start,
                end_time=fold.test_end,
                initial_balance=spec.initial_balance,
                exec_cfg=exec_cfg,
            )
            equal_weight_test_return = float(equal_weight_metrics.percentage_return)

            summary = FoldMetricsSummary(
                fold_index=fold.fold_index,
                train_return_pct=float(train_metrics.percentage_return or 0.0),
                test_return_pct=float(test_metrics.percentage_return or 0.0),
                test_max_drawdown_pct=float(test_metrics.max_drawdown_pct or 0.0),
                test_trades_count=test_metrics.total_trades or 0,
                test_win_rate_pct=(
                    float(test_metrics.behavior.win_rate_pct)
                    if test_metrics.behavior and test_metrics.behavior.win_rate_pct is not None
                    else 0.0
                ),
                test_profit_factor=(
                    float(test_metrics.behavior.profit_factor)
                    if test_metrics.behavior and test_metrics.behavior.profit_factor is not None
                    else 0.0
                ),
                baseline_test_return_pct=baseline_test_return,
                equal_weight_test_return_pct=equal_weight_test_return,
            )
            fold_summaries.append(summary)

            if on_fold_complete:
                on_fold_complete(summary)

        return WalkForwardAggregator.aggregate(run_identifier, spec.ticker_symbol, fold_summaries)

    def _execute_sub_session(
            self,
            asset: Asset,
            ds_req: BacktestDataSourceRequest,
            start_time: datetime,
            end_time: datetime,
            initial_balance: Decimal,
            exec_cfg: ExecutionConfiguration,
    ):
        request = BacktestRequest(
            ticker_symbol=asset.ticker_symbol,
            start_time=start_time,
            end_time=end_time,
            data_source=ds_req,
            initial_balance=initial_balance,
            execution=exec_cfg,
        )
        session = BacktestSession(
            ticker_symbol=asset.ticker_symbol,
            request=request,
            status=BacktestSessionStatus.RUNNING,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
        )
        runner = BacktestRunner(
            db_manager=self._db_manager,
            assets={asset.ticker_symbol: asset},
            dynamic_quantity=self._dynamic_quantity,
            data_source_resolver=self._resolver,
        )
        result = runner.run_session(session)
        return self._calculator.calculate(result)
