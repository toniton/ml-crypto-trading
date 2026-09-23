from __future__ import annotations

import pytest

from src.agent.actions.executor import AgentActionExecutor
from src.agent.actions.models import (
    ActionReason,
    ActionSeverity,
    ActionStatus,
    AgentAction,
    AgentActionType,
    AgentPermission,
)
from src.agent.actions.notification_policy import NotificationPolicy
from src.agent.actions.service import AgentActionService
from src.events.message_event_bus import MessageEventBus
from tests.unit.agent.fakes import FakeConversationStore


@pytest.fixture
def event_bus():
    return MessageEventBus()


@pytest.fixture
def conversation_store():
    return FakeConversationStore()


@pytest.fixture
def action_service(event_bus):
    return AgentActionService(
        event_bus=event_bus,
        notification_policy=NotificationPolicy(info_cooldown_seconds=10.0, warning_cooldown_seconds=5.0),
    )


def test_create_and_get_action(action_service):
    action = AgentAction(
        type=AgentActionType.SEND_MESSAGE,
        title="Test Message",
        description="A test notification",
        severity=ActionSeverity.INFO,
    )
    created = action_service.create_action(action)

    assert created.status == ActionStatus.CREATED
    retrieved = action_service.get_action(created.id)
    assert retrieved is not None
    assert retrieved.title == "Test Message"


def test_action_status_lifecycle(action_service):
    action = AgentAction(
        type=AgentActionType.RUN_ANALYSIS,
        title="Run Analysis",
        description="Analysis task",
    )
    action_service.create_action(action)
    action_service.update_status(action.id, ActionStatus.EXECUTING)
    assert action_service.get_action(action.id).status == ActionStatus.EXECUTING

    action_service.update_status(action.id, ActionStatus.COMPLETED)
    updated = action_service.get_action(action.id)
    assert updated.status == ActionStatus.COMPLETED
    assert updated.completed_at is not None


def test_notification_policy_throttling():
    policy = NotificationPolicy(info_cooldown_seconds=100.0, warning_cooldown_seconds=50.0)
    action1 = AgentAction(
        type=AgentActionType.SEND_MESSAGE,
        title="Drift Notice",
        description="Drift detected",
        reason=ActionReason(trigger="DRIFT_DETECTED", related_entities=["BTC_USD"]),
        severity=ActionSeverity.INFO,
    )
    # First time delivers
    assert policy.should_deliver(action1) is True

    # Immediate second occurrence with same trigger is throttled
    action2 = AgentAction(
        type=AgentActionType.SEND_MESSAGE,
        title="Drift Notice",
        description="Drift detected again",
        reason=ActionReason(trigger="DRIFT_DETECTED", related_entities=["BTC_USD"]),
        severity=ActionSeverity.INFO,
    )
    assert policy.should_deliver(action2) is False

    # Critical severity bypasses cooldown
    action_crit = AgentAction(
        type=AgentActionType.SEND_MESSAGE,
        title="Circuit Breaker",
        description="Halting trades",
        reason=ActionReason(trigger="CIRCUIT_BREAKER", related_entities=["BTC_USD"]),
        severity=ActionSeverity.CRITICAL,
    )
    assert policy.should_deliver(action_crit) is True


def test_executor_permission_check(mocker):
    vcs = mocker.MagicMock()
    config_service = mocker.MagicMock()
    action_service = AgentActionService()
    approval_service = mocker.MagicMock()

    # Executor with only read permissions
    executor = AgentActionExecutor(
        action_service=action_service,
        approval_service=approval_service,
        vcs=vcs,
        configuration_service=config_service,
        permissions={AgentPermission.READ_RUNTIME},
    )

    action = AgentAction(
        type=AgentActionType.SEND_MESSAGE,
        title="Unauthorized Send",
        description="Try to send message",
    )
    result = executor.plan_and_execute(action)
    assert result.status == ActionStatus.FAILED
    assert "permission" in (result.error or "").lower()
