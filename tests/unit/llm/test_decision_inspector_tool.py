from __future__ import annotations

from decimal import Decimal

import pytest

from api.interfaces.trade_action import TradeAction
from src.llm.tools.decision_inspector_tool import DecisionInspectorTool
from src.trading.decision.decision_manager import DecisionManager
from src.trading.decision.trading_decision import (
    ConsensusSnapshot,
    DecisionStatus,
    HealthEvaluation,
    MarketSnapshot,
    PortfolioSnapshot,
    RegimeSnapshot,
    RiskEvaluation,
    SizingSnapshot,
    TradingDecision,
)
from tests.unit.api_server.helpers import make_db_manager


@pytest.fixture
def db_manager(tmp_path):
    return make_db_manager(str(tmp_path / "app.db"))


@pytest.fixture
def decision_manager(db_manager):
    return DecisionManager(database_manager=db_manager)


def _seed_decision(decision_manager: DecisionManager, decision_id="dec-test-1", order_id="ord-test-1") -> TradingDecision:
    decision = TradingDecision(
        decision_id=decision_id,
        timestamp=1700000000.0,
        ticker_symbol="BTC_USD",
        exchange="CRYPTO_DOT_COM",
        trade_action=TradeAction.BUY,
        status=DecisionStatus.EXECUTED,
        resulting_order_id=order_id,
        commit_hash="commit-test-1",
        winning_strategy="HammerStrategy",
        market_snapshot=MarketSnapshot(
            close_price=Decimal("50000"),
            bid_price=Decimal("49990"),
            ask_price=Decimal("50010"),
            spread_pct=Decimal("0.0004"),
            candles_count=50,
        ),
        regime_snapshot=RegimeSnapshot(
            regime="HIGH_VOLATILITY",
            volatility=0.035,
            trend_strength=0.04,
            spread=0.0004,
            exposure_multiplier=0.5,
        ),
        consensus_snapshot=ConsensusSnapshot(
            action=TradeAction.BUY,
            votes={"HammerStrategy": True, "RSI": False},
            weights={"HammerStrategy": 1.0, "RSI": 0.5},
            factor=1.0,
            quorum=True,
            quorum_margin=0.5,
            vote_ratio=0.5,
            winning_strategy="HammerStrategy",
        ),
        sizing_snapshot=SizingSnapshot(
            formula="balance * 0.05",
            calculated_quantity=Decimal("0.025"),
            min_quantity=Decimal("0.001"),
            final_quantity=Decimal("0.025"),
            variables={"price": "50000"},
        ),
        portfolio_snapshot=PortfolioSnapshot(
            available_cash=Decimal("5000"),
            total_equity=Decimal("10000"),
            current_exposure_pct=0.5,
            asset_exposure_pct=0.25,
            drawdown_pct=0.02,
        ),
        risk_evaluation=RiskEvaluation(passed=True),
        health_evaluation=HealthEvaluation(state="TRADING", allowed=True),
    )
    decision_manager.record_decision(decision)
    return decision


def test_decision_inspector_by_decision_id(decision_manager):
    _seed_decision(decision_manager, decision_id="dec-abc", order_id="ord-abc")
    tool = DecisionInspectorTool(decision_manager=decision_manager)

    output = tool._run(decision_id="dec-abc")
    assert "=== Trading Decision dec-abc ===" in output
    assert "BTC_USD on CRYPTO_DOT_COM" in output
    assert "Resulting Order ID: ord-abc" in output
    assert "Close Price: $50000" in output
    assert "HIGH_VOLATILITY" in output
    assert "Exposure Multiplier: 0.50x" in output
    assert "Winning Strategy: HammerStrategy" in output
    assert "Risk Guard Passed: True" in output


def test_decision_inspector_by_order_id(decision_manager):
    _seed_decision(decision_manager, decision_id="dec-order-search", order_id="ord-find-me")
    tool = DecisionInspectorTool(decision_manager=decision_manager)

    output = tool._run(order_id="ord-find-me")
    assert "=== Trading Decision dec-order-search ===" in output
    assert "Resulting Order ID: ord-find-me" in output


def test_decision_inspector_list_by_symbol(decision_manager):
    _seed_decision(decision_manager, decision_id="dec-1", order_id="ord-1")
    tool = DecisionInspectorTool(decision_manager=decision_manager)

    output = tool._run(ticker_symbol="BTC_USD")
    assert "Found 1 Recent Trading Decision(s)" in output
    assert "ID: dec-1 | BTC_USD BUY | Status: EXECUTED" in output


def test_decision_inspector_not_found(decision_manager):
    tool = DecisionInspectorTool(decision_manager=decision_manager)
    output = tool._run(decision_id="dec-non-existent")
    assert "No trading decision found for ID 'dec-non-existent'" in output
