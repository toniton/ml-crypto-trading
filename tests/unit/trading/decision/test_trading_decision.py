from __future__ import annotations

from decimal import Decimal

from api.interfaces.trade_action import TradeAction
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


def _create_sample_decision(decision_id: str = "dec_123", status: DecisionStatus = DecisionStatus.EXECUTED) -> TradingDecision:
    return TradingDecision(
        decision_id=decision_id,
        timestamp=1760000000.0,
        ticker_symbol="BTC_USD",
        exchange="CRYPTO_DOT_COM",
        trade_action=TradeAction.BUY,
        status=status,
        rejection_reason=None,
        commit_hash="867d16c",
        winning_strategy="RSI_Oversold",
        resulting_order_id="ord_999",
        market_snapshot=MarketSnapshot(
            close_price=Decimal("65000.50"),
            bid_price=Decimal("65000.00"),
            ask_price=Decimal("65001.00"),
            spread_pct=Decimal("0.000015"),
            candles_count=50,
        ),
        regime_snapshot=RegimeSnapshot(
            regime="HIGH_VOLATILITY",
            volatility=0.035,
            trend_strength=0.008,
            spread=0.00015,
            exposure_multiplier=0.5,
        ),
        consensus_snapshot=ConsensusSnapshot(
            action=TradeAction.BUY,
            votes={"RSI_Oversold": True, "MACD_Bullish": True, "EMA_Trend": False},
            weights={"RSI_Oversold": 1.0, "MACD_Bullish": 1.0, "EMA_Trend": 1.0},
            factor=1.0,
            quorum=True,
            quorum_margin=1.0,
            vote_ratio=0.6667,
            winning_strategy="RSI_Oversold",
        ),
        sizing_snapshot=SizingSnapshot(
            formula="portfolio_cash * 0.25 / close",
            calculated_quantity=Decimal("0.03846"),
            min_quantity=Decimal("0.0001"),
            final_quantity=Decimal("0.03846"),
            variables={"portfolio_cash": 10000.0, "close": 65000.50},
        ),
        portfolio_snapshot=PortfolioSnapshot(
            available_cash=Decimal("10000.00"),
            total_equity=Decimal("25000.00"),
            current_exposure_pct=0.60,
            asset_exposure_pct=0.15,
            drawdown_pct=0.02,
        ),
        risk_evaluation=RiskEvaluation(
            passed=True,
            effective_max_per_asset=Decimal("0.125"),
            effective_max_total=Decimal("0.40"),
            min_quote_reserve=Decimal("0.10"),
            rejection_reason=None,
        ),
        health_evaluation=HealthEvaluation(
            state="HEALTHY",
            allowed=True,
            active_conditions=[],
        ),
        metadata={"source": "live_executor"},
    )


def test_trading_decision_serialization():
    decision = _create_sample_decision()
    data = decision.to_dict()

    assert data["decision_id"] == "dec_123"
    assert data["ticker_symbol"] == "BTC_USD"
    assert data["trade_action"] == "BUY"
    assert data["status"] == "EXECUTED"
    assert data["market_snapshot"]["close_price"] == "65000.50"
    assert data["regime_snapshot"]["regime"] == "HIGH_VOLATILITY"
    assert data["regime_snapshot"]["exposure_multiplier"] == 0.5
    assert data["consensus_snapshot"]["quorum"] is True
    assert data["consensus_snapshot"]["votes"]["RSI_Oversold"] is True
    assert data["sizing_snapshot"]["formula"] == "portfolio_cash * 0.25 / close"
    assert data["portfolio_snapshot"]["available_cash"] == "10000.00"
    assert data["risk_evaluation"]["passed"] is True
    assert data["health_evaluation"]["state"] == "HEALTHY"

    reconstructed = TradingDecision.from_dict(data)
    assert reconstructed.decision_id == decision.decision_id
    assert reconstructed.market_snapshot.close_price == Decimal("65000.50")
    assert reconstructed.regime_snapshot.exposure_multiplier == 0.5
    assert reconstructed.consensus_snapshot.quorum is True
    assert reconstructed.sizing_snapshot.calculated_quantity == Decimal("0.03846")
    assert reconstructed.portfolio_snapshot.available_cash == Decimal("10000.00")
    assert reconstructed.risk_evaluation.passed is True
    assert reconstructed.health_evaluation.allowed is True


def test_rejected_decision():
    decision = _create_sample_decision(decision_id="dec_rejected", status=DecisionStatus.REJECTED)
    decision.rejection_reason = "RISK_LIMIT_EXCEEDED"
    decision.resulting_order_id = None

    data = decision.to_dict()
    assert data["status"] == "REJECTED"
    assert data["rejection_reason"] == "RISK_LIMIT_EXCEEDED"
    assert data["resulting_order_id"] is None

    reconstructed = TradingDecision.from_dict(data)
    assert reconstructed.status == DecisionStatus.REJECTED
    assert reconstructed.rejection_reason == "RISK_LIMIT_EXCEEDED"
