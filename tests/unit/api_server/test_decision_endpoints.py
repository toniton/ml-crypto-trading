from __future__ import annotations

from decimal import Decimal

import pytest
import yaml
from fastapi.testclient import TestClient

from api.interfaces.trade_action import TradeAction
from src.agent import AgentGateway
from src.database.repositories.providers.postgres_trading_decision_repository import (
    PostgresTradingDecisionRepository,
)
from src.events.message_event_bus import MessageEventBus
from src.recorder.market_data_store import MarketDataStore
from src.server.app import ChatApp
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
from src.vcs.application.service import VCSService
from tests.unit.agent.fakes import FakeLlmAdapter
from tests.unit.api_server.helpers import (
    make_db_manager,
    make_test_llm_manager,
    make_test_trading_proxy,
)

SAMPLE_CONFIG = """
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
      buy: 1.3
      sell: 0.5
dynamic_quantity: "max(min_qty, eq * 0.1)"
"""


@pytest.fixture
def db_manager(tmp_path):
    db_mgr = make_db_manager(str(tmp_path / "app.db"))
    VCSService(db_mgr).seed_if_empty(yaml.safe_load(SAMPLE_CONFIG), author="test", message="seed")
    return db_mgr


@pytest.fixture
def event_bus():
    return MessageEventBus()


@pytest.fixture
def client(db_manager, event_bus):
    vcs = VCSService(db_manager)
    agent = AgentGateway(FakeLlmAdapter([]), vcs=vcs)
    market_store = MarketDataStore(db_manager)
    app = ChatApp.create(
        trading_proxy=make_test_trading_proxy(market_data_store=market_store),
        agent=agent,
        event_bus=event_bus,
        db_manager=db_manager,
        vcs=vcs,
        llm_manager=make_test_llm_manager(db_manager),
    )
    return TestClient(app)


def _seed_decision(db_manager, decision_id="dec-123", order_id="ord-abc-123", status=DecisionStatus.EXECUTED) -> TradingDecision:
    decision = TradingDecision(
        decision_id=decision_id,
        timestamp=1700000000.0,
        ticker_symbol="BTC_USD",
        exchange="CRYPTO_DOT_COM",
        trade_action=TradeAction.BUY,
        status=status,
        resulting_order_id=order_id,
        commit_hash="commit-123",
        winning_strategy="HammerStrategy",
        market_snapshot=MarketSnapshot(
            close_price=Decimal("50000"),
            bid_price=Decimal("49990"),
            ask_price=Decimal("50010"),
            spread_pct=Decimal("0.0004"),
            candles_count=50,
        ),
        regime_snapshot=RegimeSnapshot(
            regime="NORMAL",
            volatility=0.015,
            trend_strength=0.02,
            spread=0.0004,
            exposure_multiplier=1.0,
        ),
        consensus_snapshot=ConsensusSnapshot(
            action=TradeAction.BUY,
            votes={"HammerStrategy": True},
            weights={"HammerStrategy": 1.0},
            factor=1.0,
            quorum=True,
            quorum_margin=1.0,
            vote_ratio=1.0,
            winning_strategy="HammerStrategy",
        ),
        sizing_snapshot=SizingSnapshot(
            formula="balance * 0.1",
            calculated_quantity=Decimal("0.05"),
            min_quantity=Decimal("0.001"),
            final_quantity=Decimal("0.05"),
            variables={"price": "50000"},
        ),
        portfolio_snapshot=PortfolioSnapshot(
            available_cash=Decimal("10000"),
            total_equity=Decimal("10000"),
            current_exposure_pct=0.0,
            asset_exposure_pct=0.0,
            drawdown_pct=0.0,
        ),
        risk_evaluation=RiskEvaluation(passed=True),
    )
    with db_manager.get_unit_of_work() as uow:
        repo = uow.get_repository(PostgresTradingDecisionRepository)
        repo.save(decision)
    return decision


def test_list_decisions_empty(client):
    res = client.get("/api/v1/decisions")
    assert res.status_code == 200
    data = res.json()
    assert data["decisions"] == []
    assert data["count"] == 0


def test_list_and_filter_decisions(client, db_manager):
    _seed_decision(db_manager, decision_id="dec-1", order_id="ord-1", status=DecisionStatus.EXECUTED)
    _seed_decision(db_manager, decision_id="dec-2", order_id=None, status=DecisionStatus.REJECTED)

    res = client.get("/api/v1/decisions")
    assert res.status_code == 200
    assert res.json()["count"] == 2

    # Filter by status
    res_rejected = client.get("/api/v1/decisions?status=REJECTED")
    assert res_rejected.status_code == 200
    assert res_rejected.json()["count"] == 1
    assert res_rejected.json()["decisions"][0]["decision_id"] == "dec-2"


def test_get_decision_by_id(client, db_manager):
    _seed_decision(db_manager, decision_id="dec-exact-123", order_id="ord-999")

    res = client.get("/api/v1/decisions/dec-exact-123")
    assert res.status_code == 200
    data = res.json()
    assert data["decision_id"] == "dec-exact-123"
    assert data["resulting_order_id"] == "ord-999"
    assert data["market_snapshot"]["close_price"] == "50000"
    assert data["regime_snapshot"]["regime"] == "NORMAL"
    assert data["consensus_snapshot"]["winning_strategy"] == "HammerStrategy"


def test_get_decision_by_order_id(client, db_manager):
    _seed_decision(db_manager, decision_id="dec-xyz", order_id="order-unique-456")

    res = client.get("/api/v1/decisions/by-order/order-unique-456")
    assert res.status_code == 200
    assert res.json()["decision_id"] == "dec-xyz"

    # Fallback lookup on main endpoint
    res_fallback = client.get("/api/v1/decisions/order-unique-456")
    assert res_fallback.status_code == 200
    assert res_fallback.json()["decision_id"] == "dec-xyz"


def test_get_decision_not_found(client):
    res = client.get("/api/v1/decisions/non-existent-id")
    assert res.status_code == 404
