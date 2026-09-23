from __future__ import annotations

import uuid

from src.events.agent_events import (
    AgentActionCreatedEvent,
    AgentActionUpdatedEvent,
    AgentApprovalRequestedEvent,
    AgentMessageCreatedEvent,
)
from src.events.message_event_bus import MessageEventBus
from src.server.agent_event_projector import AgentEventProjector
from tests.unit.agent.fakes import FakeConversationStore


def _projector(bus):
    store = FakeConversationStore()
    projector = AgentEventProjector(event_bus=bus, conversation_store=store)
    projector.subscribe()
    return projector, store


def test_message_projected_to_conversation_store():
    bus = MessageEventBus()
    projector, store = _projector(bus)
    event = AgentMessageCreatedEvent(
        conversation_id="sess-1",
        message_payload={"content": "hello", "blocks": [{"type": "markdown", "content": "hello"}]},
    )
    bus.publish(event)
    messages = store.messages("sess-1")
    assert len(messages) == 1
    assert messages[0].content == "hello"
    assert messages[0].role == "assistant"


def test_projection_idempotent_for_same_event():
    bus = MessageEventBus()
    projector, store = _projector(bus)
    event = AgentMessageCreatedEvent(
        conversation_id="sess-1",
        message_payload={"content": "hello"},
    )
    bus.publish(event)
    bus.publish(event)
    assert len(store.messages("sess-1")) == 1


def test_system_conversation_resolution_when_no_id():
    bus = MessageEventBus()
    projector, store = _projector(bus)
    event = AgentMessageCreatedEvent(
        conversation_id=None,
        message_payload={"content": "autonomous alert"},
        agent_context_id="starvation_watchdog",
        server_profile_id="prod",
        user_id=None,
    )
    bus.publish(event)
    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].id == "system:prod:starvation_watchdog:system"
    assert store.messages(sessions[0].id)[0].content == "autonomous alert"


def test_action_read_model():
    bus = MessageEventBus()
    projector, _store = _projector(bus)
    action_id = uuid.uuid4().hex
    bus.publish(AgentActionCreatedEvent(
        action_id=action_id,
        action_payload={"id": action_id, "title": "T", "status": "CREATED"},
    ))
    bus.publish(AgentActionUpdatedEvent(
        action_id=action_id,
        action_payload={"id": action_id, "title": "T", "status": "PLANNED"},
    ))
    action = projector.get_action(action_id)
    assert action["status"] == "PLANNED"
    assert action["title"] == "T"
    assert [a["id"] for a in projector.list_actions()] == [action_id]


def test_approval_read_model_and_materialised_message():
    bus = MessageEventBus()
    projector, store = _projector(bus)
    bus.publish(AgentApprovalRequestedEvent(
        approval_id="ap-1",
        approval_payload={
            "approval_id": "ap-1",
            "agent_action_id": "act-1",
            "title": "Proposal",
            "base_commit": "abc",
            "asset": "BTC_USD",
            "proposed_change": {"changes": []},
        },
    ))
    approval = projector.get_approval("ap-1")
    assert approval["status"] == "PENDING"
    assert approval["title"] == "Proposal"

    # Approval card is materialised into a system conversation as a single message.
    sessions = store.list_sessions()
    assert len(sessions) == 1
    messages = store.messages(sessions[0].id)
    assert len(messages) == 1
    assert messages[0].payload["blocks"][0]["type"] == "agent_approval"
    assert messages[0].payload["blocks"][0]["approval_id"] == "ap-1"