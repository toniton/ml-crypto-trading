from __future__ import annotations

import re
import threading
import time
from typing import Any, List, Optional

from src.agent.oracle.events import OracleSummaryEvent
from src.core.interfaces.conversation_store import (
    RESERVED_AGENT_SESSION_ID,
    ConversationMessage,
    ConversationStore,
)
from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.core.severity import Severity
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
    ORACLE_COOLDOWN_SECONDS = 300.0
    ELEVATED_RISK_KEYWORDS = ("warning", "critical", "high", "breach", "halt", "block", "pause", "alert")

    def __init__(
            self,
            event_bus: EventBus,
            conversation_store: ConversationStore,
            oracle_cooldown_seconds: float = ORACLE_COOLDOWN_SECONDS,
    ):
        self._event_bus = event_bus
        self._conversation_store = conversation_store
        self._oracle_cooldown_seconds = oracle_cooldown_seconds
        self._actions: dict[str, dict] = {}
        self._approvals: dict[str, dict] = {}
        self._seen_event_ids: set[str] = set()
        self._last_oracle_fingerprint: Optional[str] = None
        self._last_oracle_emitted_at: float = 0.0
        self._hydrated: bool = False
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
                OracleSummaryEvent,
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
        elif isinstance(event, OracleSummaryEvent):
            self._on_oracle_summary(event)

    def _on_oracle_summary(self, event: OracleSummaryEvent) -> None:
        summary = event.payload
        fingerprint = "|".join(
            [
                summary.market_state,
                summary.trading_state,
                summary.risk_state,
                ";".join(summary.observations),
                ";".join(summary.recommendations),
            ]
        )
        risk_lower = summary.risk_state.lower()
        is_elevated = any(keyword in risk_lower for keyword in self.ELEVATED_RISK_KEYWORDS)
        severity = Severity.WARNING if is_elevated else Severity.INFO

        now = time.monotonic()
        with self._lock:
            unchanged = fingerprint == self._last_oracle_fingerprint
            within_cooldown = (now - self._last_oracle_emitted_at) < self._oracle_cooldown_seconds
            if unchanged and within_cooldown and not is_elevated:
                return
            self._last_oracle_fingerprint = fingerprint
            self._last_oracle_emitted_at = now

        lines = [
            "### Oracle Market & Risk Summary",
            "",
            summary.summary,
            "",
            f"- **Market state:** `{summary.market_state}`",
            f"- **Trading state:** `{summary.trading_state}`",
            f"- **Risk state:** `{summary.risk_state}`",
        ]
        if summary.observations:
            lines.append("")
            lines.append("**Observations:**")
            lines.extend(f"- {obs}" for obs in summary.observations)
        if summary.recommendations:
            lines.append("")
            lines.append("**Recommendations:**")
            lines.extend(f"- {rec}" for rec in summary.recommendations)

        content = "\n".join(lines)
        blocks = [{"type": "markdown", "content": content}]
        title = "Oracle Summary"
        preview = self._build_preview(summary.summary or content)
        message_id = f"oracle:{event.id}"

        self._event_bus.publish(
            AgentMessageCreatedEvent(
                conversation_id=RESERVED_AGENT_SESSION_ID,
                message_payload={
                    "message_id": message_id,
                    "conversation_id": RESERVED_AGENT_SESSION_ID,
                    "title": title,
                    "preview": preview,
                    "severity": severity.value,
                    "content": content,
                    "blocks": blocks,
                    "payload": {
                        "blocks": blocks,
                        "tokens": "",
                        "notification": {
                            "title": title,
                            "preview": preview,
                            "severity": severity.value,
                        },
                    },
                },
            )
        )

    @staticmethod
    def _build_preview(content: str, max_length: int = 140) -> str:
        plain = re.sub(r"[#*_`>]+", " ", content or "")
        plain = re.sub(r"\s+", " ", plain).strip()
        if len(plain) <= max_length:
            return plain
        return f"{plain[: max_length - 1].rstrip()}..."

    def _on_agent_message_created(self, event: AgentMessageCreatedEvent) -> None:
        conversation_id = self._resolve_conversation(event)
        payload = event.message_payload or {}
        message_id = str(payload.get("message_id") or event.event_id)
        self._conversation_store.append(
            conversation_id,
            ConversationMessage(
                role="assistant",
                content=payload.get("content") or "Agent message",
                message_id=message_id,
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

        conversation_id = self._resolve_conversation(event)
        self._conversation_store.append(
            conversation_id,
            ConversationMessage(
                role="assistant",
                content=f"Approval requested: {payload.get('title', '')}",
                message_id=event.approval_id,
                payload={
                    "blocks": [
                        {
                            "type": "agent_approval",
                            "approval_id": event.approval_id,
                            "action_id": payload.get("agent_action_id"),
                            "action_type": payload.get("action_type"),
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
        with self._lock:
            self._approvals[event.approval_id] = payload

    def _on_agent_approval_resolved(self, event: AgentApprovalResolvedEvent) -> None:
        with self._lock:
            existing = self._approvals.get(event.approval_id)
            title = (
                (event.approval_payload or {}).get("title")
                or (existing or {}).get("title")
                or "configuration change"
            )

        if not event.error_code:
            conversation_id = self._resolve_conversation(event)
            decision_label = "Approved" if event.decision.lower() == "approve" else "Rejected"
            decision_data = {
                "action": event.decision.lower(),
                "approval_id": event.approval_id,
                "title": title,
            }
            if event.approval_payload and event.approval_payload.get("commit_hash"):
                decision_data["commit_hash"] = event.approval_payload["commit_hash"]
            if event.approval_payload and event.approval_payload.get("experiment_id"):
                decision_data["experiment_id"] = event.approval_payload["experiment_id"]
            if event.approval_payload and event.approval_payload.get("action_type"):
                decision_data["action_type"] = event.approval_payload["action_type"]
            subject = (
                "experiment proposal"
                if decision_data.get("action_type") == "RUN_EXPERIMENT"
                else "configuration change"
            )
            self._conversation_store.append(
                conversation_id,
                ConversationMessage(
                    role="assistant",
                    content=f"{decision_label} {subject}: {title}",
                    message_id=f"decision:{event.approval_id}",
                    payload={"decision": decision_data},
                    conversation_id=conversation_id,
                ),
            )

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
                approval.pop("error_code", None)
                approval.pop("error_message", None)
            if event.approval_payload:
                approval.update(event.approval_payload)

    def _upsert_action(self, action_id: str, payload: dict) -> None:
        with self._lock:
            existing = self._actions.get(action_id) or {}
            existing.update(payload)
            self._actions[action_id] = existing

    def _hydrate_session(self, session_id: str) -> None:
        for msg in self._conversation_store.messages(session_id):
            if not msg.payload:
                continue
            action_data = msg.payload.get("agent_action")
            if isinstance(action_data, dict) and "id" in action_data:
                self._actions.setdefault(action_data["id"], action_data)
            for block in msg.payload.get("blocks", []):
                if isinstance(block, dict) and block.get("type") == "agent_approval":
                    app_id = block.get("approval_id")
                    if app_id:
                        self._approvals.setdefault(app_id, block)

    def _ensure_hydrated(self) -> None:
        if self._hydrated:
            return
        with self._lock:
            if self._hydrated:
                return
            self._hydrated = True
            try:
                for session in self._conversation_store.list_sessions():
                    self._hydrate_session(session.id)
            except Exception:
                pass

    def _resolve_conversation(self, event: Any) -> str:
        conversation_id = None
        if isinstance(event, AgentMessageCreatedEvent):
            conversation_id = event.conversation_id
        elif isinstance(event, (AgentApprovalRequestedEvent, AgentApprovalResolvedEvent)) and event.approval_payload:
            conversation_id = event.approval_payload.get("conversation_id")

        if conversation_id:
            return conversation_id

        return self._conversation_store.get_or_create(RESERVED_AGENT_SESSION_ID)

    # Read-model queries used by REST routes.

    def list_actions(
            self,
            conversation_id: Optional[str] = None,
            status: Optional[str] = None,
            limit: int = 50,
    ) -> List[dict]:
        self._ensure_hydrated()
        with self._lock:
            actions = list(self._actions.values())
        if conversation_id:
            actions = [a for a in actions if a.get("conversation_id") == conversation_id]
        if status:
            actions = [a for a in actions if a.get("status") == status]
        actions.sort(key=lambda a: str(a.get("created_at") or ""), reverse=True)
        return actions[:limit]

    def get_action(self, action_id: str) -> Optional[dict]:
        self._ensure_hydrated()
        with self._lock:
            return self._actions.get(action_id)

    def list_approvals(self, status: Optional[str] = None, limit: int = 50) -> List[dict]:
        self._ensure_hydrated()
        with self._lock:
            approvals = list(self._approvals.values())
        if status:
            approvals = [a for a in approvals if a.get("status") == status]
        approvals.sort(key=lambda a: str(a.get("requested_at") or ""), reverse=True)
        return approvals[:limit]

    def get_approval(self, approval_id: str) -> Optional[dict]:
        self._ensure_hydrated()
        with self._lock:
            approval = self._approvals.get(approval_id)
            if approval is not None:
                return approval
            for app in self._approvals.values():
                if approval_id in (
                        app.get("id"),
                        app.get("approval_id"),
                        app.get("agent_action_id"),
                        app.get("action_id"),
                        app.get("proposal_id"),
                ):
                    return app
        # Check in conversation store directly
        message = self._conversation_store.get_message(approval_id)
        if message and message.payload:
            for block in message.payload.get("blocks", []):
                if isinstance(block, dict) and block.get("type") in ("agent_approval", "approval", "configuration_diff"):
                    b_app_id = block.get("approval_id") or block.get("proposal_id") or message.message_id
                    action_id = block.get("action_id") or block.get("agent_action_id")
                    if approval_id in (b_app_id, action_id, message.message_id):
                        with self._lock:
                            self._approvals[approval_id] = block
                        return block
        # Fallback: scan sessions
        try:
            for session in self._conversation_store.list_sessions():
                for msg in self._conversation_store.messages(session.id):
                    if msg.payload and "blocks" in msg.payload:
                        for block in msg.payload.get("blocks", []):
                            if isinstance(block, dict) and block.get("type") in ("agent_approval", "approval", "configuration_diff"):
                                b_app_id = block.get("approval_id") or block.get("proposal_id") or msg.message_id
                                action_id = block.get("action_id") or block.get("agent_action_id")
                                if approval_id in (b_app_id, action_id, msg.message_id):
                                    with self._lock:
                                        self._approvals[approval_id] = block
                                    return block
        except Exception:
            pass
        return None
