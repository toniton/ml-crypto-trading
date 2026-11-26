from __future__ import annotations

from decimal import Decimal
import time

import yaml

from api.interfaces.backtest_request import BacktestDataSourceType
from api.interfaces.experiment import CandidateType, ExperimentCandidate
from api.interfaces.trade_action import TradeAction
from src.agent.automation.experiment_suggester import NoSignalsExperimentSuggester
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.monitoring.activity_state import AssetActivityState
from src.backtest.analysis.drift_detector import DriftReport
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.events.agent_events import TradingActivityAnomalyDetectedEvent
from src.server.services.experiment_application_service import (
    ExperimentApplicationService,
)
from src.trading.strategies.strategy_registry import StrategyRegistry
from src.vcs.application.service import VCSService
from tests.unit.api_server.helpers import make_db_manager

CONFIG_WITH_STRATEGIES = """
assets:
  - name: "Bitcoin (Crypto.com)"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 0.00005
    quote_decimals: 2
    quantity_decimals: 5
    candles_timeframe: "MIN1"
    schedule: 1
    consensus:
      buy: 1.4
      sell: 0.9
    strategies:
      - name: "HammerAccumulationStrategy"
        type: "STATIC"
        class_name: "HammerAccumulationStrategy"
        action: "BUY"
        enabled: true
        weight: 0.6
      - name: "ShootingStarSellStrategy"
        type: "STATIC"
        class_name: "ShootingStarSellStrategy"
        action: "SELL"
        enabled: false
        weight: 0.8
dynamic_quantity: "max(min_qty, eq * 0.1)"
"""


def _build_registry() -> StrategyRegistry:
    return StrategyRegistry(
        predefined=[
            StrategyConfig(
                name="HammerAccumulationStrategy",
                type=StrategyType.STATIC,
                class_name="HammerAccumulationStrategy",
                action=TradeAction.BUY,
            ),
            StrategyConfig(
                name="RsiOversoldBuy",
                type=StrategyType.DYNAMIC,
                action=TradeAction.BUY,
                expression="rsi(14) < 25",
            ),
            StrategyConfig(
                name="RsiOverboughtSell",
                type=StrategyType.DYNAMIC,
                action=TradeAction.SELL,
                expression="rsi(14) > 78 and position_qty > 0",
            ),
            StrategyConfig(
                name="TrendFollowingBuy",
                type=StrategyType.DYNAMIC,
                action=TradeAction.BUY,
                expression="sma(20) > sma(50) and close > sma(20)",
            ),
        ]
    )


def _make_config_service(tmp_path) -> ConfigurationService:
    db_mgr = make_db_manager(str(tmp_path / "suggester.db"))
    vcs = VCSService(db_mgr)
    vcs.seed_if_empty(
        yaml.safe_load(CONFIG_WITH_STRATEGIES),
        author="test",
        message="seed",
    )
    return ConfigurationService(vcs=vcs)


def test_suggester_uses_drift_window_and_generates_candidates(tmp_path):
    config_service = _make_config_service(tmp_path)
    suggester = NoSignalsExperimentSuggester(
        configuration_service=config_service,
        strategy_registry=_build_registry(),
    )
    event = TradingActivityAnomalyDetectedEvent(
        asset="BTC_USD",
        anomaly_kind="NO_SIGNALS",
        threshold=63.0,
        detected_at=str(time.time()),
    )
    drift = DriftReport(
        ticker_symbol="BTC_USD",
        simulated_fill_count=2,
        live_fill_count=0,
        simulated_quantity=Decimal("0.01000"),
        live_quantity=Decimal("0"),
        simulated_average_price=Decimal("65000"),
        live_average_price=None,
        fill_count_drift=2,
        quantity_drift=Decimal("0.01000"),
        price_drift=None,
        drifted=True,
        window_start="2026-11-25T19:00:00+00:00",
        window_end="2026-11-25T20:35:00+00:00",
    )

    proposal = suggester.suggest(event, drift=drift)
    cfg = proposal.experiment_config

    assert cfg["ticker_symbol"] == "BTC_USD"
    assert cfg["data_source"]["source_type"] == BacktestDataSourceType.MARKET_DATA.value
    assert cfg["period"]["start_time"] == "2026-11-25T19:00:00+00:00"
    assert cfg["period"]["end_time"] == "2026-11-25T20:35:00+00:00"
    assert proposal.observed_window["source"] == "backtest_drift_replay"
    assert proposal.diagnostic_summary["drifted"] is True
    assert proposal.diagnostic_summary["fill_count_drift"] == 2

    cand_ids = [c["candidate_id"] for c in cfg["candidates"]]
    assert "cand_current" in cand_ids
    assert "cand_reenable_strategies" in cand_ids
    assert "cand_tuned_weights_thresholds" in cand_ids
    assert "cand_additional_strategies" in cand_ids
    assert "cand_alternative_mix" in cand_ids

    added_cand = next(
        c for c in cfg["candidates"] if c["candidate_id"] == "cand_additional_strategies"
    )
    added_names = {s["name"] for s in added_cand["strategies_to_add"]}
    assert "RsiOverboughtSell" in added_names
    assert "HammerAccumulationStrategy" not in added_names


def test_suggester_falls_back_to_recent_window_when_drift_absent(tmp_path):
    config_service = _make_config_service(tmp_path)
    suggester = NoSignalsExperimentSuggester(
        configuration_service=config_service,
        strategy_registry=_build_registry(),
        default_lookback_seconds=3600.0,
    )
    now = 1764100000.0
    event = TradingActivityAnomalyDetectedEvent(
        asset="BTC_USD",
        anomaly_kind="NO_SIGNALS",
        threshold=63.0,
        detected_at=str(now),
    )
    state = AssetActivityState(
        ticker_symbol="BTC_USD",
        last_market_data_at=now - 38.0,
        last_evaluation_at=now - 38.0,
    )

    proposal = suggester.suggest(event, state=state, drift=None)

    assert proposal.observed_window["source"] == "recent_market_data_window"
    assert proposal.experiment_config["period"]["start_time"] < proposal.experiment_config["period"]["end_time"]


def test_apply_candidate_weights_handles_custom_combination():
    existing = [
        StrategyConfig(
            name="HammerAccumulationStrategy",
            type=StrategyType.STATIC,
            class_name="HammerAccumulationStrategy",
            action=TradeAction.BUY,
            enabled=True,
            weight=0.6,
        ),
        StrategyConfig(
            name="ShootingStarSellStrategy",
            type=StrategyType.STATIC,
            class_name="ShootingStarSellStrategy",
            action=TradeAction.SELL,
            enabled=False,
            weight=0.8,
        ),
    ]
    candidate = ExperimentCandidate(
        candidate_id="cand_custom",
        name="Custom Strategy Mix",
        candidate_type=CandidateType.CUSTOM_COMBINATION,
        strategy_weights={
            "HammerAccumulationStrategy": 0.9,
            "ShootingStarSellStrategy": 1.0,
            "TrendFollowingBuy": 1.2,
        },
        strategy_enabled_overrides={"ShootingStarSellStrategy": True},
        strategies_to_add=[
            {
                "name": "TrendFollowingBuy",
                "type": "DYNAMIC",
                "action": "BUY",
                "expression": "sma(20) > sma(50) and close > sma(20)",
                "enabled": True,
                "weight": 1.0,
            }
        ],
    )

    result = ExperimentApplicationService._apply_candidate_weights(candidate, existing)
    assert result is not None
    updated_strategies, commit_msg = result
    by_name = {s.name: s for s in updated_strategies}

    assert "Custom Strategy Mix" in commit_msg
    assert set(by_name.keys()) == {
        "HammerAccumulationStrategy",
        "ShootingStarSellStrategy",
        "TrendFollowingBuy",
    }
    assert by_name["HammerAccumulationStrategy"].weight == 0.9
    assert by_name["ShootingStarSellStrategy"].enabled is True
    assert by_name["ShootingStarSellStrategy"].weight == 1.0
    assert by_name["TrendFollowingBuy"].weight == 1.2
