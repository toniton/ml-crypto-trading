from __future__ import annotations

import threading
from typing import Any, List, Optional

from src.core.interfaces.conversation_store import ConversationMessage, ConversationStore
from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.events.agent_events import (
    AgentActionCompletedEvent,
    AgentActionCreatedEvent,
    AgentActionFailedEvent,
    AgentActionUpdatedEvent,
    AgentApprovalRequestedEvent,
    AgentApprovalResolvedEvent,
    AgentMessageCreatedEvent,
)
from src.events.message_event_bus import CallbackSubscription
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class AgentEventProjector(ApplicationLoggingMixin):
    def __init__(self, event_bus: EventBus, conversation_store: ConversationStore):
        self._event_bus = event_bus
        self._conversation_store = conversation_store
        self._actions: dict[str, dict] = {}
        self._approvals: dict[str, dict] = {}
        self._seen_event_ids: set[str] = set()
        self._lock = threading.Lock()
        self._subscriptions: list[str] = []

    def subscribe(self) -> None:
        for event_cls in (
                AgentMessageCreatedEvent,
                AgentActionCreatedEvent,
                AgentActionUpdatedEvent,
                AgentActionCompletedEvent,
                AgentActionFailedEvent,
                AgentApprovalRequestedEvent,
                AgentApprovalResolvedEvent,
        ):
            self._subscriptions.append(
                self._event_bus.subscribe(event_cls.__name__, CallbackSubscription(self._on_event))
            )

    def close(self) -> None:
        for subscription_id in self._subscriptions:
            self._event_bus.unsubscribe(subscription_id)
        self._subscriptions.clear()

    def _on_event(self, event: Event) -> None:
        event_id = event.id
        if event_id:
            with self._lock:
                if event_id in self._seen_event_ids:
                    return
                self._seen_event_ids.add(event_id)

        if isinstance(event, AgentMessageCreatedEvent):
            self._on_agent_message_created(event)
        elif isinstance(event, AgentActionCreatedEvent):
            self._on_agent_action_created(event)
        elif isinstance(event, AgentActionUpdatedEvent):
            self._on_agent_action_updated(event)
        elif isinstance(event, AgentActionCompletedEvent):
            self._on_agent_action_completed(event)
        elif isinstance(event, AgentActionFailedEvent):
            self._on_agent_action_failed(event)
        elif isinstance(event, AgentApprovalRequestedEvent):
            self._on_agent_approval_requested(event)
        elif isinstance(event, AgentApprovalResolvedEvent):
            self._on_agent_approval_resolved(event)

    def _on_agent_message_created(self, event: AgentMessageCreatedEvent) -> None:
        conversation_id = self._resolve_conversation(event)
        payload = event.message_payload or {}
        self._conversation_store.append(
            conversation_id,
            ConversationMessage(
                role="assistant",
                content=payload.get("content") or "Agent message",
                message_id=event.event_id,
                payload=payload.get("payload") or {"blocks": payload.get("blocks") or []},
                conversation_id=conversation_id,
            ),
        )

    def _on_agent_action_created(self, event: AgentActionCreatedEvent) -> None:
        self._upsert_action(event.action_id, event.action_payload or {})

    def _on_agent_action_updated(self, event: AgentActionUpdatedEvent) -> None:
        self._upsert_action(event.action_id, event.action_payload or {})

    def _on_agent_action_completed(self, event: AgentActionCompletedEvent) -> None:
        with self._lock:
            action = self._actions.get(event.action_id)
            if action is not None:
                action["status"] = "COMPLETED"
                if event.result_payload:
                    action["result_payload"] = event.result_payload

    def _on_agent_action_failed(self, event: AgentActionFailedEvent) -> None:
        with self._lock:
            action = self._actions.get(event.action_id)
            if action is not None:
                action["status"] = "FAILED"
                action["error"] = event.error

    def _on_agent_approval_requested(self, event: AgentApprovalRequestedEvent) -> None:
        payload = event.approval_payload or {}
        payload["status"] = payload.get("status") or "PENDING"
        with self._lock:
            self._approvals[event.approval_id] = payload

        conversation_id = self._resolve_conversation(event)
        self._conversation_store.append(
            conversation_id,
            ConversationMessage(
                role="assistant",
                content=f"Approval requested: {payload.get('title', '')}",
                message_id=event.event_id,
                payload={
                    "blocks": [
                        {
                            "type": "agent_approval",
                            "approval_id": event.approval_id,
                            "action_id": payload.get("agent_action_id"),
                            "title": payload.get("title"),
                            "description": payload.get("description"),
                            "base_commit": payload.get("base_commit"),
                            "asset": payload.get("asset"),
                            "proposed_change": payload.get("proposed_change"),
                            "status": "pending",
                        }
                    ]
                },
                conversation_id=conversation_id,
            ),
        )

    def _on_agent_approval_resolved(self, event: AgentApprovalResolvedEvent) -> None:
        with self._lock:
            approval = self._approvals.get(event.approval_id)
            if approval is None:
                approval = {"approval_id": event.approval_id}
                self._approvals[event.approval_id] = approval
            if event.error_code:
                approval["status"] = "ERROR"
                approval["error_code"] = event.error_code
                approval["error_message"] = event.error_message
            else:
                approval["status"] = event.decision.upper()
            if event.approval_payload:
                approval.update(event.approval_payload)

    def _upsert_action(self, action_id: str, payload: dict) -> None:
        with self._lock:
            existing = self._actions.get(action_id) or {}
            existing.update(payload)
            self._actions[action_id] = existing

    def _resolve_conversation(self, event: Any) -> str:
        conversation_id = None
        if isinstance(event, AgentMessageCreatedEvent):
            conversation_id = event.conversation_id
        elif isinstance(event, AgentApprovalRequestedEvent) and event.approval_payload:
            conversation_id = event.approval_payload.get("conversation_id")

        if conversation_id:
            return conversation_id

        agent_context_id = (
            event.agent_context_id
            if isinstance(event, AgentMessageCreatedEvent) and event.agent_context_id
            else "agent"
        )
        server_profile_id = (
            event.server_profile_id
            if isinstance(event, AgentMessageCreatedEvent) and event.server_profile_id
            else "default"
        )
        user_id = (
            event.user_id
            if isinstance(event, AgentMessageCreatedEvent) and event.user_id
            else "system"
        )
        session_id = f"system:{server_profile_id}:{agent_context_id}:{user_id}"
        return self._conversation_store.get_or_create(session_id)

    # Read-model queries used by REST routes.

    def list_actions(
            self,
            conversation_id: Optional[str] = None,
            status: Optional[str] = None,
            limit: int = 50,
    ) -> List[dict]:
        with self._lock:
            actions = list(self._actions.values())
        if conversation_id:
            actions = [a for a in actions if a.get("conversation_id") == conversation_id]
        if status:
            actions = [a for a in actions if a.get("status") == status]
        actions.sort(key=lambda a: str(a.get("created_at") or ""), reverse=True)
        return actions[:limit]

    def get_action(self, action_id: str) -> Optional[dict]:
        with self._lock:
            return self._actions.get(action_id)

    def list_approvals(self, status: Optional[str] = None, limit: int = 50) -> List[dict]:
        with self._lock:
            approvals = list(self._approvals.values())
        if status:
            approvals = [a for a in approvals if a.get("status") == status]
        approvals.sort(key=lambda a: str(a.get("requested_at") or ""), reverse=True)
        return approvals[:limit]

    def get_approval(self, approval_id: str) -> Optional[dict]:
        with self._lock:
            return self._approvals.get(approval_id)
