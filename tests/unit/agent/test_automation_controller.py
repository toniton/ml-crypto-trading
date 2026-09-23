from __future__ import annotations

import time
import uuid
from typing import Optional
from unittest.mock import MagicMock

from src.agent.actions.models import AgentActionType
from src.agent.automation.automation_controller import AutomationController
from src.agent.automation.investigate_activity_anomaly import InvestigateActivityAnomaly
from src.agent.monitoring.activity_state import AssetActivityState
from src.agent.monitoring.starvation_watchdog import StarvationWatchdog
from src.events.agent_event_metadata import AgentEventMetadata
from src.events.agent_events import (
    AgentActionPlanRequestedEvent,
    AgentApprovalDecisionRequestedEvent,
    TradingActivityAnomalyDetectedEvent,
)
from src.events.message_event_bus import CallbackSubscription, MessageEventBus


class FakeProvider:
    def __init__(self, state: Optional[AssetActivityState], started_at: float):
        self._state = state
        self._started = started_at

    @property
    def started_at(self) -> float:
        return self._started

    def state_for(self, ticker_symbol: str) -> Optional[AssetActivityState]:
        return self._state

    def states(self) -> list:
        return [self._state] if self._state else []


def _controller(executor, approval_service, provider=None, authority=None):
    bus = MessageEventBus()
    provider = provider or FakeProvider(None, time.time())
    investigation = InvestigateActivityAnomaly(activity_provider=provider)
    watchdog = StarvationWatchdog(
        activity_provider=provider, assets=[], event_bus=bus
    )
    controller = AutomationController(
        event_bus=bus,
        executor=executor,
        approval_service=approval_service,
        investigation=investigation,
        watchdog=watchdog,
        authority=authority,
    )
    return controller, bus


def _capture(bus, event_type):
    captured = []

    def handler(event):
        captured.append(event)

    bus.subscribe(event_type, CallbackSubscription(handler))
    return captured


def test_action_plan_executed_with_correlation_ids():
    executor = MagicMock()
    controller, _bus = _controller(executor, MagicMock())
    request_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    event = AgentActionPlanRequestedEvent(
        action_type="SEND_MESSAGE",
        title="Hello",
        agent_metadata=AgentEventMetadata(
            request_id=request_id, correlation_id=correlation_id
        ),
    )
    controller._dispatch(event)
    assert executor.plan_and_execute.call_count == 1
    action = executor.plan_and_execute.call_args.args[0]
    assert action.type == AgentActionType.SEND_MESSAGE
    assert action.request_id == str(request_id)
    assert action.correlation_id == str(correlation_id)


def test_action_plan_idempotent_by_request_id():
    executor = MagicMock()
    controller, _bus = _controller(executor, MagicMock())
    request_id = uuid.uuid4()
    event_a = AgentActionPlanRequestedEvent(
        action_type="SEND_MESSAGE",
        title="A",
        agent_metadata=AgentEventMetadata(request_id=request_id, correlation_id=uuid.uuid4()),
    )
    event_b = AgentActionPlanRequestedEvent(
        action_type="SEND_MESSAGE",
        title="B",
        agent_metadata=AgentEventMetadata(request_id=request_id, correlation_id=uuid.uuid4()),
    )
    controller._dispatch(event_a)
    controller._dispatch(event_b)
    assert executor.plan_and_execute.call_count == 1


def test_autonomous_authority_blocks_state_changing():
    executor = MagicMock()
    controller, bus = _controller(executor, MagicMock())
    failed = _capture(bus, "AgentActionFailedEvent")
    event = AgentActionPlanRequestedEvent(
        action_type="APPLY_CONFIGURATION",
        title="Commit",
        source="starvation_watchdog",
        agent_metadata=AgentEventMetadata(request_id=uuid.uuid4(), correlation_id=uuid.uuid4()),
    )
    controller._dispatch(event)
    assert executor.plan_and_execute.call_count == 0
    assert len(failed) == 1
    assert "not permitted" in failed[0].error


def test_user_actions_bypass_authority_gate():
    executor = MagicMock()
    controller, _bus = _controller(executor, MagicMock())
    event = AgentActionPlanRequestedEvent(
        action_type="APPLY_CONFIGURATION",
        title="User commit",
        source="user",
        agent_metadata=AgentEventMetadata(request_id=uuid.uuid4(), correlation_id=uuid.uuid4()),
    )
    controller._dispatch(event)
    assert executor.plan_and_execute.call_count == 1


def test_anomaly_emits_diagnostic_message():
    executor = MagicMock()
    stale = AssetActivityState(ticker_symbol="BTC_USD", last_market_data_at=time.time() - 10000)
    controller, _bus = _controller(
        executor, MagicMock(), provider=FakeProvider(stale, time.time() - 10000)
    )
    event = TradingActivityAnomalyDetectedEvent(
        asset="BTC_USD",
        anomaly_kind="NO_MARKET_DATA",
        threshold=240.0,
    )
    controller._dispatch(event)
    assert executor.plan_and_execute.call_count == 1
    action = executor.plan_and_execute.call_args.args[0]
    assert action.type == AgentActionType.SEND_MESSAGE
    assert action.reason.trigger == "STARVATION_DETECTED"
    assert "BTC_USD" in action.reason.related_entities


def test_approval_decision_dispatched():
    approval_service = MagicMock()
    controller, _bus = _controller(MagicMock(), approval_service)
    event = AgentApprovalDecisionRequestedEvent(
        approval_id="ap-1",
        decision="approve",
        author="alice",
        agent_metadata=AgentEventMetadata(request_id=uuid.uuid4(), correlation_id=uuid.uuid4()),
    )
    controller._dispatch(event)
    approval_service.decide_approval.assert_called_once_with(
        "ap-1", "approve", author="alice", decision_notes=None
    )


def test_approval_error_publishes_structured_event():
    approval_service = MagicMock()
    approval_service.decide_approval.side_effect = ValueError("out of date")
    controller, bus = _controller(MagicMock(), approval_service)
    resolved = _capture(bus, "AgentApprovalResolvedEvent")
    event = AgentApprovalDecisionRequestedEvent(
        approval_id="ap-1",
        decision="approve",
        agent_metadata=AgentEventMetadata(request_id=uuid.uuid4(), correlation_id=uuid.uuid4()),
    )
    controller._dispatch(event)
    assert len(resolved) == 1
    assert resolved[0].error_code == "APPROVAL_CONFLICT"
    assert "out of date" in resolved[0].error_message