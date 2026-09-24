from __future__ import annotations

from decimal import Decimal

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.events.decision_models import (
    ActorType,
    DecisionRecord,
    DecisionType,
    EntityRef,
)
from src.trading.events import (
    ConsensusEvaluatedEvent,
    OrderSubmittedEvent,
)


def _order() -> Order:
    return Order(
        uuid="o-123",
        provider_name="BACKTEST",
        ticker_symbol="BTC_USD",
        price=Decimal("100"),
        quantity="1.0",
        trade_action=TradeAction.BUY,
        created_time=100.0,
    )


def test_trading_event_causal_metadata_default_and_setter():
    event = OrderSubmittedEvent(symbol="BTC_USD", order=_order())
    assert event.event_id is not None
    assert event.actor_type == "SYSTEM"
    assert event.asset == "BTC_USD"

    event.set_causality(
        correlation_id="corr-1",
        causation_id="caus-1",
        source="watchdog",
        actor_type=ActorType.WATCHDOG.value,
        actor_id="watchdog-1",
        commit_hash="c12345",
    )

    data = event.to_dict()
    assert data["correlation_id"] == "corr-1"
    assert data["causation_id"] == "caus-1"
    assert data["source"] == "watchdog"
    assert data["actor_type"] == "WATCHDOG"
    assert data["actor_id"] == "watchdog-1"
    assert data["commit_hash"] == "c12345"
    assert data["asset"] == "BTC_USD"


def test_consensus_evaluated_event_structure():
    event = ConsensusEvaluatedEvent(
        symbol="BTC_USD",
        decision="BUY",
        buy_votes=2,
        sell_votes=0,
        total_strategies=2,
        quorum_met=True,
        evaluated_at=1000.0,
        factors={"buy": 1.3, "sell": 0.5},
    )
    assert event.decision == "BUY"
    assert event.quorum_met is True
    assert event.buy_votes == 2
    assert event.to_dict()["payload"]["buy_votes"] == 2


def test_decision_record_serialization():
    decision = DecisionRecord(
        actor_type=ActorType.AGENT,
        decision_type=DecisionType.INVESTIGATION_OUTCOME,
        summary="Propose pausing SOL_USD",
        rationale="Trading starvation detected.",
        evidence_ids=["evt-1", "bt-2"],
        entities=[EntityRef(type="ASSET", id="SOL_USD"), EntityRef(type="BACKTEST", id="bt-2")],
        proposed_action_id="act-3",
    )
    d_dict = decision.to_dict()
    assert d_dict["actor_type"] == "AGENT"
    assert d_dict["decision_type"] == "INVESTIGATION_OUTCOME"
    assert len(d_dict["entities"]) == 2
    assert d_dict["entities"][0] == {"type": "ASSET", "id": "SOL_USD"}
    assert d_dict["evidence_ids"] == ["evt-1", "bt-2"]
