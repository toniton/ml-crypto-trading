from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.trade_action import TradeAction
from src.database.repositories.trading_decision_repository import (
    TradingDecisionRepository,
)
from src.trading.decision.decision_manager import DecisionManager
from src.trading.decision.trading_decision import (
    ConsensusSnapshot,
    DecisionStatus,
    MarketSnapshot,
    PortfolioSnapshot,
    RegimeSnapshot,
    RiskEvaluation,
    SizingSnapshot,
    TradingDecision,
)


def _make_dummy_decision(decision_id: str = "dec-100", order_id: str = "ord-100") -> TradingDecision:
    return TradingDecision(
        decision_id=decision_id,
        timestamp=1700000000.0,
        ticker_symbol="BTC_USD",
        exchange="CRYPTO_DOT_COM",
        trade_action=TradeAction.BUY,
        status=DecisionStatus.EXECUTED,
        resulting_order_id=order_id,
        commit_hash="commit-123",
        winning_strategy="TestStrategy",
        market_snapshot=MarketSnapshot(close_price=Decimal("50000"), candles_count=10),
        regime_snapshot=RegimeSnapshot(
            regime="BULLISH",
            volatility=0.01,
            trend_strength=0.5,
            spread=0.0001,
            exposure_multiplier=1.0,
        ),
        consensus_snapshot=ConsensusSnapshot(
            action=TradeAction.BUY,
            votes={"TestStrategy": True},
            weights={"TestStrategy": 1.0},
            factor=1.0,
            quorum=True,
            quorum_margin=0.5,
            vote_ratio=1.0,
        ),
        sizing_snapshot=SizingSnapshot(min_quantity=Decimal("0.001"), variables={}),
        portfolio_snapshot=PortfolioSnapshot(
            available_cash=Decimal("5000"),
            total_equity=Decimal("10000"),
            current_exposure_pct=0.5,
            asset_exposure_pct=0.25,
            drawdown_pct=0.0,
        ),
        risk_evaluation=RiskEvaluation(passed=True),
    )


def test_decision_manager_delegates_to_repository():
    mock_repo = MagicMock(spec=TradingDecisionRepository)
    dummy = _make_dummy_decision("dec-1", "ord-1")
    mock_repo.get.return_value = dummy
    mock_repo.get_by_order_id.return_value = dummy
    mock_repo.get_by_ticker_symbol.return_value = [dummy]
    mock_repo.get_by_commit_hash.return_value = [dummy]
    mock_repo.list_decisions.return_value = [dummy]

    manager = DecisionManager(repository=mock_repo)

    manager.record_decision(dummy)
    mock_repo.save.assert_called_once_with(dummy)

    assert manager.get_decision("dec-1") == dummy
    mock_repo.get.assert_called_once_with("dec-1")

    assert manager.get_decision_by_order_id("ord-1") == dummy
    mock_repo.get_by_order_id.assert_called_once_with("ord-1")

    assert manager.get_decisions_by_symbol("BTC_USD") == [dummy]
    mock_repo.get_by_ticker_symbol.assert_called_once_with("BTC_USD", limit=50)

    assert manager.get_decisions_by_commit("commit-123") == [dummy]
    mock_repo.get_by_commit_hash.assert_called_once_with("commit-123")

    assert manager.list_decisions(ticker_symbol="BTC_USD", limit=10) == [dummy]
    mock_repo.list_decisions.assert_called_once_with(
        ticker_symbol="BTC_USD", exchange=None, status=None, since=None, until=None, limit=10, offset=0
    )
