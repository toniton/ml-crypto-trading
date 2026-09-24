from __future__ import annotations

from decimal import Decimal

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.agent.monitoring.starvation_watchdog import TradingActivityAnomalyDetectedEvent
from src.events.agent_events import AgentApprovalRequestedEvent, AgentApprovalResolvedEvent
from src.events.message_event_bus import MessageEventBus
from src.server.timeline_projector import TimelineProjector
from src.trading.events import (
    ConsensusEvaluatedEvent,
    OrderFilledEvent,
    OrderSubmittedEvent,
)
from src.vcs.application.events import RefChangedEvent


def _order() -> Order:
    return Order(
        uuid="ord-123",
        provider_name="CRYPTO_DOT_COM",
        ticker_symbol="BTC_USD",
        price=Decimal("50000"),
        quantity="0.5",
        trade_action=TradeAction.BUY,
        created_time=100.0,
    )


def test_order_events_projected():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    ev1 = OrderSubmittedEvent(symbol="BTC_USD", order=_order())
    ev1.correlation_id = "c-1"
    bus.publish(ev1)

    ev2 = OrderFilledEvent(symbol="BTC_USD", order=_order())
    ev2.correlation_id = "c-1"
    bus.publish(ev2)

    items = projector.list_items()
    assert len(items) == 2
    # Newest first
    assert items[0]["title"] == "Order Filled: BTC_USD"
    assert items[0]["correlation_id"] == "c-1"
    assert items[0]["category"] == "TRADING"
    assert items[1]["title"] == "Order Submitted: BTC_USD TradeAction.BUY"
    assert items[1]["primary_entity"]["id"] == "ord-123"

    projector.close()


def test_consensus_event_projected():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    bus.publish(ConsensusEvaluatedEvent(
        symbol="ETH_USD",
        decision="BUY",
        quorum_met=True,
        buy_votes=3,
        sell_votes=0,
    ))

    items = projector.list_items(category="DECISION")
    assert len(items) == 1
    assert items[0]["category"] == "DECISION"
    assert items[0]["title"] == "Consensus Evaluated: ETH_USD -> BUY"
    assert items[0]["metadata"]["buy_votes"] == 3


def test_watchdog_anomaly_projected():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    bus.publish(TradingActivityAnomalyDetectedEvent(
        asset="DOGE_USD",
        anomaly_kind="MARKET_DATA_STARVATION",
        threshold=120.0,
    ))

    items = projector.list_items(severity="WARNING")
    assert len(items) == 1
    assert items[0]["actor_type"] == "WATCHDOG"
    assert items[0]["primary_entity"]["id"] == "DOGE_USD"


def test_approval_events_projected():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    bus.publish(AgentApprovalRequestedEvent(
        approval_id="app-1",
        approval_payload={"title": "Adjust BTC Quorum", "asset": "BTC_USD"},
    ))
    bus.publish(AgentApprovalResolvedEvent(
        approval_id="app-1",
        decision="approved",
    ))

    items = projector.list_items(category="APPROVAL")
    assert len(items) == 2
    assert items[0]["title"] == "Proposal Decision: APPROVED"
    assert items[1]["title"] == "Approval Requested: Adjust BTC Quorum"


def test_vcs_event_projected():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    bus.publish(RefChangedEvent(
        ref="refs/heads/main",
        commit_hash="abcdef123456",
    ))

    items = projector.list_items(category="VCS")
    assert len(items) == 1
    assert items[0]["title"] == "VCS Updated: refs/heads/main"
    assert items[0]["primary_entity"]["id"] == "abcdef123456"


def test_filter_by_entity_type_and_id():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    bus.publish(OrderSubmittedEvent(symbol="BTC_USD", order=_order()))
    bus.publish(ConsensusEvaluatedEvent(symbol="ETH_USD", decision="HOLD", quorum_met=False, buy_votes=0, sell_votes=0))

    btc_items = projector.list_items(entity_type="ASSET", entity_id="BTC_USD")
    assert len(btc_items) == 1
    assert btc_items[0]["metadata"]["symbol"] == "BTC_USD"

    eth_items = projector.list_items(entity_type="ASSET", entity_id="ETH_USD")
    assert len(eth_items) == 1
    assert eth_items[0]["metadata"]["decision"] == "HOLD"


def test_max_items_eviction():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus, max_items=3)
    projector.subscribe()

    for i in range(5):
        bus.publish(ConsensusEvaluatedEvent(symbol=f"SYM_{i}", decision="HOLD", quorum_met=False, buy_votes=0, sell_votes=0))

    items = projector.list_items()
    assert len(items) == 3
    assert items[0]["title"] == "Consensus Evaluated: SYM_4 -> HOLD"
    assert items[2]["title"] == "Consensus Evaluated: SYM_2 -> HOLD"
