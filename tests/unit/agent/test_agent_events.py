from __future__ import annotations

import uuid

from src.events.agent_event_metadata import AgentEventMetadata
from src.events.agent_events import (
    AgentActionPlanRequestedEvent,
    AgentApprovalDecisionRequestedEvent,
    AgentMessageCreatedEvent,
)


def test_agent_event_carries_envelope():
    request_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    causation_id = uuid.uuid4()
    event = AgentMessageCreatedEvent(
        conversation_id="sess-1",
        message_payload={"content": "hello"},
        agent_metadata=AgentEventMetadata(
            request_id=request_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            sequence_number=3,
        ),
    )
    assert event.request_id == request_id
    assert event.correlation_id == correlation_id
    assert event.causation_id == causation_id
    assert event.sequence_number == 3
    assert event.event_id == event.id


def test_command_event_defaults_to_user_source():
    event = AgentActionPlanRequestedEvent(
        action_type="SEND_MESSAGE",
        title="T",
        agent_metadata=AgentEventMetadata(correlation_id=uuid.uuid4()),
    )
    assert event.source == "user"
    assert event.request_id is None


def test_approval_decision_event_fields():
    event = AgentApprovalDecisionRequestedEvent(
        approval_id="ap-1",
        decision="approve",
        author="alice",
        decision_notes="ok",
    )
    assert event.approval_id == "ap-1"
    assert event.author == "alice"


def test_event_payload_contains_metadata():
    event = AgentMessageCreatedEvent(
        agent_metadata=AgentEventMetadata(correlation_id=uuid.uuid4(), sequence_number=1),
    )
    payload = event.payload
    assert payload["agent_metadata"]["sequence_number"] == 1


def test_with_metadata_attaches_envelope():
    from src.events.agent_events import with_metadata

    metadata = AgentEventMetadata(correlation_id=uuid.uuid4())
    event = with_metadata(AgentActionPlanRequestedEvent(), metadata)
    assert event.correlation_id == metadata.correlation_id