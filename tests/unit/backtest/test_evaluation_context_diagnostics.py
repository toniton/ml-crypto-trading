from __future__ import annotations

from decimal import Decimal

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.backtest_request import (BacktestDataSourceRequest,
                                             BacktestDataSourceType,
                                             BacktestRequest,
                                             ExecutionConfiguration)
from api.interfaces.experiment import ExperimentSpec
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.backtest.backtest_event_bus import (BacktestDiagnosticEventBus,
                                             BacktestEventBus)
from src.backtest.backtest_result_collector import BacktestResultCollector
from src.backtest.data.backtest_data_source_resolver import \
    BacktestDataSourceResolver
from src.backtest.domain.session import BacktestSession
from src.backtest.runner.backtest_runner import (
    EXECUTOR_DIAGNOSTIC_EVENT_TYPES, BacktestRunner)
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.database.repositories.mappers.backtest_db_vs_entity_mapper import \
    BacktestDBVSEntityMapper
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.recorder.market_data_store import MarketDataStore
from src.server.services.experiment_application_service import \
    ExperimentApplicationService
from src.trading.consensus.consensus_factor import ConsensusFactor
from src.trading.events.domain_events import (DecisionRejectedEvent,
                                              DecisionRejectedReason,
                                              MarketDataEvent,
                                              MarketRegimeObservedEvent,
                                              OrderSubmittedEvent,
                                              SignalGeneratedEvent)
from src.trading.strategies.strategy_registry import StrategyRegistry


def _sample_session() -> BacktestSession:
    request = BacktestRequest(
        ticker_symbol="BTC_USD",
        data_source=BacktestDataSourceRequest(
            source_type=BacktestDataSourceType.MARKET_DATA,
        ),
        initial_balance=Decimal("10000"),
        execution=ExecutionConfiguration(),
    )
    return BacktestSession(id="bt_diag_1", ticker_symbol="BTC_USD", request=request)


def test_collector_tracks_dataset_regime_and_risk_block_diagnostics():
    bus = BacktestEventBus()
    collector = BacktestResultCollector(bus)

    bus.publish(
        MarketDataEvent(
            ticker_symbol="BTC_USD",
            market_data=MarketData(
                volume=Decimal("10"),
                high_price=Decimal("61000"),
                low_price=Decimal("60000"),
                close_price=Decimal("60500"),
                timestamp=1764097200.0,
            ),
        )
    )
    bus.publish(
        MarketDataEvent(
            ticker_symbol="BTC_USD",
            market_data=MarketData(
                volume=Decimal("12"),
                high_price=Decimal("61200"),
                low_price=Decimal("60100"),
                close_price=Decimal("60800"),
                timestamp=1764100800.0,
            ),
        )
    )

    bus.publish(
        MarketRegimeObservedEvent(
            symbol="BTC_USD", regime="ILLIQUID", observed_at=1764097200.0
        )
    )
    bus.publish(
        MarketRegimeObservedEvent(
            symbol="BTC_USD", regime="ILLIQUID", observed_at=1764099000.0
        )
    )
    bus.publish(
        MarketRegimeObservedEvent(
            symbol="BTC_USD", regime="RANGING", observed_at=1764100800.0
        )
    )

    for _ in range(4):
        bus.publish(
            SignalGeneratedEvent(
                symbol="BTC_USD",
                action="BUY",
                generated_at=1764099000.0,
            )
        )

    bus.publish(
        DecisionRejectedEvent(
            symbol="BTC_USD",
            action="BUY",
            reason=DecisionRejectedReason.RISK_REJECTED.value,
            details={"reason": "Market regime is ILLIQUID: new orders prohibited"},
        )
    )
    bus.publish(
        DecisionRejectedEvent(
            symbol="BTC_USD",
            action="BUY",
            reason=DecisionRejectedReason.RISK_REJECTED.value,
            details={
                "reason": "Asset concentration limit exceeded for BTC_USD: projected 14.26% > limit 12.50%"
            },
        )
    )
    # Non-risk rejection should not increment risk_blocked_signals
    bus.publish(
        DecisionRejectedEvent(
            symbol="BTC_USD",
            action="BUY",
            reason=DecisionRejectedReason.NO_QUORUM.value,
        )
    )

    result = collector.build_result(_sample_session())
    assert result.diagnostics is not None
    assert result.diagnostics.dataset_bar_count == 2
    assert result.diagnostics.dataset_duration_seconds == 3600.0
    assert result.diagnostics.total_signals == 4
    assert result.diagnostics.risk_blocked_signals == 2
    assert result.diagnostics.risk_block_reasons == {
        "ILLIQUID regime": 1,
        "Asset concentration limit": 1,
    }
    assert result.diagnostics.regime_counts == {"ILLIQUID": 2, "RANGING": 1}

    dao = BacktestDBVSEntityMapper.result_to_dao(result)
    metrics = dao.data["metrics"]
    assert metrics["dataset_context"]["bar_count"] == 2
    assert metrics["signal_diagnostics"]["risk_blocked_pct"] == 50.0
    assert metrics["regime_counts"] == {"ILLIQUID": 2, "RANGING": 1}


def test_experiment_evaluation_context_aggregates_baseline_and_all_arms():
    spec = ExperimentSpec(
        name="BTC Anomaly",
        ticker_symbol="BTC_USD",
        base_commit_hash="abc1234",
        branch_id="branch-1",
    )
    candidate_reports = {
        "cand_current": {
            "candidate_id": "cand_current",
            "backtest": {
                "dataset_context": {
                    "bar_count": 1440,
                    "start_time": "2026-11-25T19:00:00+00:00",
                    "end_time": "2026-11-25T20:35:00+00:00",
                    "duration_seconds": 5700.0,
                },
                "regime_counts": {"ILLIQUID": 82, "RANGING": 18},
                "signal_diagnostics": {
                    "total_signals": 0,
                    "risk_blocked_signals": 0,
                    "risk_blocked_pct": None,
                    "risk_block_reasons": {},
                },
            },
        },
        "cand_additional": {
            "candidate_id": "cand_additional",
            "backtest": {
                "signal_diagnostics": {
                    "total_signals": 100,
                    "risk_blocked_signals": 95,
                    "risk_blocked_pct": 95.0,
                    "risk_block_reasons": {
                        "ILLIQUID regime": 90,
                        "Asset concentration limit": 5,
                    },
                },
            },
        },
    }

    ctx = ExperimentApplicationService._build_evaluation_context(
        spec=spec,
        candidate_reports=candidate_reports,
        vcs_service=None,
    )

    assert ctx["dataset"]["bar_count"] == 1440
    assert ctx["dataset"]["duration_seconds"] == 5700.0
    assert ctx["market_regime"]["dominant"] == "ILLIQUID"
    assert ctx["market_regime"]["distribution"][0]["pct"] == 82.0
    assert ctx["portfolio_risk_blocks"]["baseline"]["total_signals"] == 0
    assert ctx["portfolio_risk_blocks"]["all_candidates"]["blocked_pct"] == 95.0
    assert ctx["portfolio_risk_blocks"]["all_candidates"]["top_reasons"][0] == {
        "reason": "ILLIQUID regime",
        "count": 90,
    }


def test_diagnostic_event_bus_forwards_only_allowlisted_events():
    bus = BacktestEventBus()
    collector = BacktestResultCollector(bus)
    diagnostic_bus = BacktestDiagnosticEventBus(bus, EXECUTOR_DIAGNOSTIC_EVENT_TYPES)

    diagnostic_bus.publish(
        MarketDataEvent(
            ticker_symbol="DOGE_USD",
            market_data=MarketData(
                volume=Decimal("0"),
                high_price=Decimal("0.15"),
                low_price=Decimal("0.14"),
                close_price=Decimal("0.145"),
                timestamp=1764097200.0,
            ),
        )
    )
    diagnostic_bus.publish(
        OrderSubmittedEvent(symbol="DOGE_USD", order=None)  # type: ignore[arg-type]
    )
    diagnostic_bus.publish(
        MarketRegimeObservedEvent(
            symbol="DOGE_USD",
            regime="ILLIQUID",
            observed_at=1764097200.0,
        )
    )
    diagnostic_bus.publish(
        SignalGeneratedEvent(
            symbol="DOGE_USD",
            action="BUY",
            generated_at=1764097200.0,
        )
    )
    diagnostic_bus.publish(
        DecisionRejectedEvent(
            symbol="DOGE_USD",
            action="BUY",
            reason=DecisionRejectedReason.RISK_REJECTED.value,
            details={"reason": "Market regime is ILLIQUID: new orders prohibited"},
        )
    )

    result = collector.build_result(_sample_session())
    assert result.market_series == []
    assert result.orders == []
    assert result.diagnostics is not None
    assert result.diagnostics.regime_counts == {"ILLIQUID": 1}
    assert result.diagnostics.total_signals == 1
    assert result.diagnostics.risk_blocked_signals == 1
    assert result.diagnostics.risk_block_reasons == {"ILLIQUID regime": 1}


def test_backtest_runner_populates_regime_and_signal_diagnostics():
    store = MarketDataStore()
    base_ts = 1764097200
    for idx in range(6):
        ts = float(base_ts + idx * 60)
        price = Decimal("0.1400") + Decimal("0.0005") * idx
        market_data = MarketData(
            volume=Decimal("0"),
            high_price=price + Decimal("0.0005"),
            low_price=price - Decimal("0.0005"),
            close_price=price,
            bid_price=price - Decimal("0.0001"),
            ask_price=price + Decimal("0.0001"),
            timestamp=ts,
        )
        store.record("DOGE_USD", market_data)

    strategy_config = StrategyConfig(
        name="AlwaysBuy",
        type=StrategyType.DYNAMIC,
        action=TradeAction.BUY,
        expression="close > 0",
        enabled=True,
        weight=1.0,
    )
    asset = Asset(
        name="Dogecoin",
        base_ticker_symbol="DOGE",
        quote_ticker_symbol="USD",
        quote_decimals=4,
        min_quantity=Decimal("1"),
        quantity_decimals=0,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=Timeframe.MIN1,
        exchange=ExchangeProvidersEnum.BACKTEST,
        enabled=True,
        consensus=ConsensusFactor(buy=1.0, sell=1.0),
        strategies=[strategy_config],
    )
    strategy_registry = StrategyRegistry([strategy_config])
    runner = BacktestRunner(
        assets={"DOGE_USD": asset},
        strategy_registry=strategy_registry,
        data_source_resolver=BacktestDataSourceResolver(
            market_data_store=store,
            dataset_service=None,
        ),
    )
    request = BacktestRequest(
        ticker_symbol="DOGE_USD",
        data_source=BacktestDataSourceRequest(
            source_type=BacktestDataSourceType.MARKET_DATA,
        ),
        initial_balance=Decimal("10000"),
        execution=ExecutionConfiguration(),
    )

    result = runner.run_one(request)
    assert result.diagnostics is not None
    assert result.diagnostics.dataset_bar_count == 6
    assert result.diagnostics.regime_counts.get("ILLIQUID", 0) > 0
    assert result.diagnostics.total_signals > 0
    assert result.diagnostics.risk_blocked_signals > 0
    assert result.diagnostics.risk_block_reasons.get("ILLIQUID regime", 0) > 0
