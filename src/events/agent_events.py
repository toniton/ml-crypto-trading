from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.events.agent_event import AgentEvent
from src.events.agent_event_metadata import AgentEventMetadata


@dataclass
class AgentMessageCreatedEvent(AgentEvent):
    EVENT_TYPE = "agent_message_created"
    conversation_id: Optional[str] = None
    message_payload: dict[str, Any] = None
    agent_context_id: Optional[str] = None
    server_profile_id: Optional[str] = None
    user_id: Optional[str] = None


@dataclass
class AgentActionCreatedEvent(AgentEvent):
    EVENT_TYPE = "agent_action_created"
    action_id: str = ""
    action_payload: dict[str, Any] = None


@dataclass
class AgentActionUpdatedEvent(AgentEvent):
    EVENT_TYPE = "agent_action_updated"
    action_id: str = ""
    action_payload: dict[str, Any] = None


@dataclass
class AgentApprovalRequestedEvent(AgentEvent):
    EVENT_TYPE = "agent_approval_requested"
    approval_id: str = ""
    approval_payload: dict[str, Any] = None


@dataclass
class AgentApprovalResolvedEvent(AgentEvent):
    EVENT_TYPE = "agent_approval_resolved"
    approval_id: str = ""
    decision: str = ""
    approval_payload: dict[str, Any] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class AgentActionCompletedEvent(AgentEvent):
    EVENT_TYPE = "agent_action_completed"
    action_id: str = ""
    result_payload: dict[str, Any] = None


@dataclass
class AgentActionFailedEvent(AgentEvent):
    EVENT_TYPE = "agent_action_failed"
    action_id: str = ""
    error: str = ""


@dataclass
class AgentActionPlanRequestedEvent(AgentEvent):
    EVENT_TYPE = "agent_action_plan_requested"
    action_type: str = ""
    title: str = ""
    description: str = ""
    conversation_id: Optional[str] = None
    payload: dict[str, Any] = None
    reason: Optional[dict[str, Any]] = None
    severity: str = "INFO"
    requires_approval: bool = False
    source: str = "user"


@dataclass
class AgentApprovalDecisionRequestedEvent(AgentEvent):
    EVENT_TYPE = "agent_approval_decision_requested"
    approval_id: str = ""
    decision: str = ""
    author: str = "user"
    decision_notes: Optional[str] = None


@dataclass
class TradingActivityAnomalyDetectedEvent(AgentEvent):
    EVENT_TYPE = "trading_activity_anomaly_detected"
    asset: str = ""
    anomaly_kind: str = ""
    activity_state: dict[str, Any] = None
    threshold: float = 0.0
    detected_at: Optional[str] = None


def with_metadata(event: AgentEvent, metadata: AgentEventMetadata) -> AgentEvent:
    event.agent_metadata = metadata
    return event
