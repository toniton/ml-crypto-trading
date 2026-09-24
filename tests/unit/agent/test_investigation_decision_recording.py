from __future__ import annotations

import time
from typing import Optional

from src.agent.automation.investigate_activity_anomaly import InvestigateActivityAnomaly
from src.agent.monitoring.activity_state import AssetActivityState
from src.events.agent_events import TradingActivityAnomalyDetectedEvent
from src.events.decision_models import AgentDecisionRecordedEvent, DecisionType
from src.events.message_event_bus import CallbackSubscription, MessageEventBus


class FakeActivityProvider:
    def __init__(self, state: Optional[AssetActivityState] = None):
        self._state = state

    @property
    def started_at(self) -> float:
        return time.time() - 3600

    def state_for(self, _ticker_symbol: str) -> Optional[AssetActivityState]:
        return self._state

    def states(self) -> list:
        return [self._state] if self._state else []


def test_investigation_emits_decision_recorded_event_for_diagnostic():
    bus = MessageEventBus()
    events: list[AgentDecisionRecordedEvent] = []
    bus.subscribe(AgentDecisionRecordedEvent.__name__, CallbackSubscription(events.append))

    state = AssetActivityState(ticker_symbol="BTC_USD", last_market_data_at=time.time() - 500)
    investigation = InvestigateActivityAnomaly(
        activity_provider=FakeActivityProvider(state),
        event_bus=bus,
    )

    anomaly_event = TradingActivityAnomalyDetectedEvent(
        asset="BTC_USD",
        anomaly_kind="NO_MARKET_DATA",
        threshold=240.0,
    )
    anomaly_event.set_causality(correlation_id="corr-anomaly-1", causation_id="cause-parent-1")

    decision = investigation.investigate(anomaly_event)

    assert decision.kind == "diagnostic"
    assert len(events) == 1
    ev = events[0]
    assert ev.decision.decision_type == DecisionType.INVESTIGATION_OUTCOME
    assert ev.decision.summary == "Connectivity or data feed problem"
    assert "No market data" in ev.decision.rationale
    assert ev.decision.entities[0].type == "ASSET"
    assert ev.decision.entities[0].id == "BTC_USD"
    assert anomaly_event.event_id in ev.decision.evidence_ids
    assert ev.correlation_id == "corr-anomaly-1"
    assert ev.causation_id == "cause-parent-1"
    assert ev.actor_type == "AGENT"
    assert ev.source == "investigate_activity_anomaly"


def test_investigation_emits_decision_recorded_event_for_proposal():
    bus = MessageEventBus()
    events: list[AgentDecisionRecordedEvent] = []
    bus.subscribe(AgentDecisionRecordedEvent.__name__, CallbackSubscription(events.append))

    state = AssetActivityState(
        ticker_symbol="ETH_USD",
        last_market_data_at=time.time() - 10,
        last_signal_at=time.time() - 10,
        last_order_at=None,
    )
    investigation = InvestigateActivityAnomaly(
        activity_provider=FakeActivityProvider(state),
        event_bus=bus,
    )

    anomaly_event = TradingActivityAnomalyDetectedEvent(
        asset="ETH_USD",
        anomaly_kind="NO_ORDERS",
        threshold=300.0,
    )
    anomaly_event.set_causality(correlation_id="corr-prop-2", causation_id="cause-prop-2")

    decision = investigation.investigate(anomaly_event)

    assert decision.kind == "proposal"
    assert len(events) == 1
    ev = events[0]
    assert ev.decision.summary == "Risk or configuration gating"
    assert ev.decision.entities[0].id == "ETH_USD"
    assert ev.correlation_id == "corr-prop-2"
