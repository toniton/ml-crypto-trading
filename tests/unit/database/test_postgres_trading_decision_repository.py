from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.interfaces.trade_action import TradeAction
from src.database.repositories.providers.postgres_trading_decision_repository import (
    PostgresTradingDecisionRepository,
)
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
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


def setup_in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def _make_decision(
    decision_id: str,
    ticker: str = "BTC_USD",
    order_id: str | None = None,
    commit_hash: str = "867d16c",
    status: DecisionStatus = DecisionStatus.EXECUTED,
    ts: float = 1760000000.0,
) -> TradingDecision:
    return TradingDecision(
        decision_id=decision_id,
        timestamp=ts,
        ticker_symbol=ticker,
        exchange="CRYPTO_DOT_COM",
        trade_action=TradeAction.BUY,
        status=status,
        rejection_reason=None if status == DecisionStatus.EXECUTED else "NO_QUORUM",
        commit_hash=commit_hash,
        winning_strategy="RSI_Oversold",
        resulting_order_id=order_id,
        market_snapshot=MarketSnapshot(
            close_price=Decimal("65000.00"),
            bid_price=Decimal("64999.00"),
            ask_price=Decimal("65001.00"),
            spread_pct=Decimal("0.00003"),
            candles_count=50,
        ),
        regime_snapshot=RegimeSnapshot(
            regime="NORMAL",
            volatility=0.015,
            trend_strength=0.005,
            spread=0.0001,
            exposure_multiplier=1.0,
        ),
        consensus_snapshot=ConsensusSnapshot(
            action=TradeAction.BUY,
            votes={"RSI": True, "MACD": True},
            weights={"RSI": 1.0, "MACD": 1.0},
            factor=1.0,
            quorum=True,
            quorum_margin=1.0,
            vote_ratio=1.0,
            winning_strategy="RSI",
        ),
        sizing_snapshot=SizingSnapshot(
            formula="close * 0.1",
            calculated_quantity=Decimal("0.05"),
            min_quantity=Decimal("0.0001"),
            final_quantity=Decimal("0.05"),
            variables={"close": 65000.0},
        ),
        portfolio_snapshot=PortfolioSnapshot(
            available_cash=Decimal("50000.00"),
            total_equity=Decimal("100000.00"),
            current_exposure_pct=0.50,
            asset_exposure_pct=0.10,
            drawdown_pct=0.01,
        ),
        risk_evaluation=RiskEvaluation(
            passed=True,
            effective_max_per_asset=Decimal("0.25"),
            effective_max_total=Decimal("0.80"),
            min_quote_reserve=Decimal("0.10"),
            rejection_reason=None,
        ),
        health_evaluation=HealthEvaluation(
            state="HEALTHY",
            allowed=True,
            active_conditions=[],
        ),
        metadata={"run_id": "test_run_1"},
    )


def test_save_and_get_decision():
    session = setup_in_memory_db()
    repo = PostgresTradingDecisionRepository(database_session=session)

    decision = _make_decision("dec_001", ticker="BTC_USD", order_id="ord_abc")
    saved = repo.save(decision)
    assert saved.decision_id == "dec_001"

    fetched = repo.get("dec_001")
    assert fetched is not None
    assert fetched.decision_id == "dec_001"
    assert fetched.ticker_symbol == "BTC_USD"
    assert fetched.market_snapshot.close_price == Decimal("65000.00")
    assert fetched.consensus_snapshot.quorum is True
    assert fetched.resulting_order_id == "ord_abc"
    assert fetched.metadata == {"run_id": "test_run_1"}


def test_get_by_order_id():
    session = setup_in_memory_db()
    repo = PostgresTradingDecisionRepository(database_session=session)

    decision = _make_decision("dec_002", ticker="ETH_USD", order_id="ord_xyz")
    repo.save(decision)

    fetched = repo.get_by_order_id("ord_xyz")
    assert fetched is not None
    assert fetched.decision_id == "dec_002"
    assert fetched.ticker_symbol == "ETH_USD"

    assert repo.get_by_order_id("non_existent_order") is None


def test_get_by_ticker_and_commit():
    session = setup_in_memory_db()
    repo = PostgresTradingDecisionRepository(database_session=session)

    repo.save(_make_decision("dec_10", ticker="SOL_USD", commit_hash="c1", ts=100.0))
    repo.save(_make_decision("dec_11", ticker="SOL_USD", commit_hash="c2", ts=200.0))
    repo.save(_make_decision("dec_12", ticker="AVAX_USD", commit_hash="c1", ts=300.0))

    sol_decisions = repo.get_by_ticker_symbol("SOL_USD")
    assert len(sol_decisions) == 2
    assert sol_decisions[0].decision_id == "dec_11"  # ordered by desc ts

    c1_decisions = repo.get_by_commit_hash("c1")
    assert len(c1_decisions) == 2


def test_list_decisions_filters():
    session = setup_in_memory_db()
    repo = PostgresTradingDecisionRepository(database_session=session)

    repo.save(_make_decision("dec_a", ticker="BTC_USD", status=DecisionStatus.EXECUTED, ts=1000.0))
    repo.save(_make_decision("dec_b", ticker="BTC_USD", status=DecisionStatus.REJECTED, ts=2000.0))
    repo.save(_make_decision("dec_c", ticker="ETH_USD", status=DecisionStatus.EXECUTED, ts=3000.0))

    executed_btc = repo.list_decisions(ticker_symbol="BTC_USD", status=DecisionStatus.EXECUTED.value)
    assert len(executed_btc) == 1
    assert executed_btc[0].decision_id == "dec_a"

    all_btc = repo.list_decisions(ticker_symbol="BTC_USD")
    assert len(all_btc) == 2
