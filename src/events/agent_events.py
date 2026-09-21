from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.events.trading_event import TradingEvent


@dataclass
class AgentMessageCreatedEvent(TradingEvent):
    EVENT_TYPE = "agent_message_created"
    conversation_id: Optional[str] = None
    message_payload: dict[str, Any] = None


@dataclass
class AgentActionCreatedEvent(TradingEvent):
    EVENT_TYPE = "agent_action_created"
    action_id: str = ""
    action_payload: dict[str, Any] = None


@dataclass
class AgentActionUpdatedEvent(TradingEvent):
    EVENT_TYPE = "agent_action_updated"
    action_id: str = ""
    action_payload: dict[str, Any] = None


@dataclass
class AgentApprovalRequestedEvent(TradingEvent):
    EVENT_TYPE = "agent_approval_requested"
    approval_id: str = ""
    approval_payload: dict[str, Any] = None


@dataclass
class AgentApprovalResolvedEvent(TradingEvent):
    EVENT_TYPE = "agent_approval_resolved"
    approval_id: str = ""
    decision: str = ""
    approval_payload: dict[str, Any] = None


@dataclass
class AgentActionCompletedEvent(TradingEvent):
    EVENT_TYPE = "agent_action_completed"
    action_id: str = ""
    result_payload: dict[str, Any] = None


@dataclass
class AgentActionFailedEvent(TradingEvent):
    EVENT_TYPE = "agent_action_failed"
    action_id: str = ""
    error: str = ""
