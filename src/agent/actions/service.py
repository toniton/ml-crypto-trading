from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.agent.actions.models import (
    ActionStatus,
    AgentAction,
    AgentApprovalRequest,
    ApprovalStatus,
)
from src.agent.actions.notification_policy import NotificationPolicy
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.configuration.models import ConfigChange, ConfigurationProposal
from src.core.interfaces.conversation_store import ConversationMessage, ConversationStore
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
from src.logging.agent_logging_mixin import AgentLoggingMixin
from src.vcs.application.service import VCSService


class AgentActionService(AgentLoggingMixin):
    """Manages the lifecycle and state transitions of autonomous and semi-autonomous agent actions."""

    def __init__(
            self,
            event_bus: Optional[EventBus] = None,
            conversation_store: Optional[ConversationStore] = None,
            notification_policy: Optional[NotificationPolicy] = None,
    ):
        self._event_bus = event_bus
        self._conversation_store = conversation_store
        self._notification_policy = notification_policy or NotificationPolicy()
        self._actions: Dict[str, AgentAction] = {}

    def create_action(self, action: AgentAction) -> AgentAction:
        action.status = ActionStatus.CREATED
        self._actions[action.id] = action

        if self._event_bus:
            self._event_bus.publish(
                AgentActionCreatedEvent(
                    action_id=action.id,
                    action_payload=action.model_dump(mode="json"),
                )
            )
        return action

    def update_status(
            self,
            action_id: str,
            status: ActionStatus,
            error: Optional[str] = None,
            completed_at: Optional[datetime] = None,
    ) -> Optional[AgentAction]:
        action = self._actions.get(action_id)
        if not action:
            return None

        action.status = status
        if error:
            action.error = error
        if completed_at or status in (ActionStatus.COMPLETED, ActionStatus.FAILED):
            action.completed_at = completed_at or datetime.now(timezone.utc)

        if self._event_bus:
            if status == ActionStatus.COMPLETED:
                self._event_bus.publish(
                    AgentActionCompletedEvent(
                        action_id=action.id,
                        result_payload=action.payload,
                    )
                )
            elif status == ActionStatus.FAILED:
                self._event_bus.publish(
                    AgentActionFailedEvent(
                        action_id=action.id,
                        error=error or "Action failed",
                    )
                )
            else:
                self._event_bus.publish(
                    AgentActionUpdatedEvent(
                        action_id=action.id,
                        action_payload=action.model_dump(mode="json"),
                    )
                )
        return action

    def get_action(self, action_id: str) -> Optional[AgentAction]:
        return self._actions.get(action_id)

    def list_actions(
            self,
            conversation_id: Optional[str] = None,
            status: Optional[ActionStatus] = None,
            limit: int = 50,
    ) -> List[AgentAction]:
        actions = list(self._actions.values())
        if conversation_id:
            actions = [a for a in actions if a.conversation_id == conversation_id]
        if status:
            actions = [a for a in actions if a.status == status]
        actions.sort(key=lambda a: a.created_at, reverse=True)
        return actions[:limit]

    def resolve_conversation_id(self, conversation_id: Optional[str] = None) -> str:
        """Resolves target conversation, defaulting to the latest active database session."""
        if conversation_id and conversation_id != "default":
            return conversation_id
        if self._conversation_store:
            try:
                sessions = self._conversation_store.list_sessions()
                if sessions:
                    return sessions[0].id
            except Exception:
                pass
            return self._conversation_store.get_or_create(None)
        return conversation_id or "default"

    def send_proactive_message(
            self,
            conversation_id: Optional[str],
            message_id: str,
            content: str,
            blocks: List[dict],
            action: Optional[AgentAction] = None,
            force: bool = False,
    ) -> None:
        """Emits a proactive message to the conversation store and event bus."""
        if action and not force and not self._notification_policy.should_deliver(action):
            self.agent_logger.info(
                f"Proactive message throttled by policy for action {action.id}"
            )
            return

        resolved_id = self.resolve_conversation_id(conversation_id)
        if action:
            action.conversation_id = resolved_id

        payload = {"blocks": blocks, "tokens": ""}
        if action:
            payload["agent_action"] = action.model_dump(mode="json")

        if self._conversation_store:
            self._conversation_store.append(
                resolved_id,
                ConversationMessage(
                    role="assistant",
                    content=content,
                    message_id=message_id,
                    payload=payload,
                ),
            )

        if self._event_bus:
            self._event_bus.publish(
                AgentMessageCreatedEvent(
                    conversation_id=resolved_id,
                    message_payload={
                        "message_id": message_id,
                        "content": content,
                        "blocks": blocks,
                        "payload": payload,
                        "action": action.model_dump(mode="json") if action else None,
                    },
                )
            )


class AgentApprovalService(AgentLoggingMixin):
    """Enforces state-bound, human-in-the-loop approvals against VCS configurations."""

    def __init__(
            self,
            vcs: VCSService,
            configuration_service: ConfigurationService,
            action_service: AgentActionService,
            event_bus: Optional[EventBus] = None,
            conversation_store: Optional[ConversationStore] = None,
    ):
        self._vcs = vcs
        self._configuration_service = configuration_service
        self._action_service = action_service
        self._event_bus = event_bus
        self._conversation_store = conversation_store
        self._approvals: Dict[str, AgentApprovalRequest] = {}

    def request_approval(self, request: AgentApprovalRequest) -> AgentApprovalRequest:
        self._approvals[request.id] = request
        self._action_service.update_status(
            request.agent_action_id, ActionStatus.WAITING_FOR_USER
        )

        if self._event_bus:
            self._event_bus.publish(
                AgentApprovalRequestedEvent(
                    approval_id=request.id,
                    approval_payload=request.model_dump(mode="json"),
                )
            )
        return request

    def get_approval(self, approval_id: str) -> Optional[AgentApprovalRequest]:
        return self._approvals.get(approval_id)

    def list_approvals(
            self, status: Optional[ApprovalStatus] = None, limit: int = 50
    ) -> List[AgentApprovalRequest]:
        approvals = list(self._approvals.values())
        if status:
            approvals = [a for a in approvals if a.status == status]
        approvals.sort(key=lambda a: a.requested_at, reverse=True)
        return approvals[:limit]

    def decide_approval(
            self,
            approval_id: str,
            action: str,  # "approve" or "reject"
            author: str = "user",
            decision_notes: Optional[str] = None,
    ) -> Tuple[AgentApprovalRequest, Optional[str], List[str]]:
        """Resolves an approval. If approved, checks base_commit against current VCS HEAD."""
        approval = self._approvals.get(approval_id)
        if not approval:
            raise KeyError(f"Approval request '{approval_id}' not found.")

        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval request is already in status '{approval.status.value}'.")

        now = datetime.now(timezone.utc)
        approval.responded_at = now
        approval.decision_notes = decision_notes

        if action == "reject":
            approval.status = ApprovalStatus.REJECTED
            self._action_service.update_status(approval.agent_action_id, ActionStatus.REJECTED)
            self._publish_resolved(approval, "reject")
            return approval, None, []

        # Validate VCS state consistency: base_commit must be equal to current HEAD
        current_head = self._vcs.head("HEAD").hash
        if approval.base_commit != current_head:
            approval.status = ApprovalStatus.EXPIRED
            self._action_service.update_status(
                approval.agent_action_id,
                ActionStatus.FAILED,
                error=f"Base commit {approval.base_commit[:8]} is no longer HEAD ({current_head[:8]}).",
            )
            raise ValueError(
                f"Cannot approve: Base commit '{approval.base_commit[:8]}' is out of date. "
                f"Current HEAD is '{current_head[:8]}'. The proposal must be regenerated."
            )

        # Convert proposed_change into ConfigurationProposal if present
        proposal_dict = approval.proposed_change
        changes = [
            ConfigChange(**c) if isinstance(c, dict) else c
            for c in proposal_dict.get("changes", [])
        ]
        proposal = ConfigurationProposal(
            summary=approval.title,
            changes=changes,
            risks=proposal_dict.get("risks", []),
            expected_effect=proposal_dict.get("expected_effect") or "",
        )

        validation = self._configuration_service.validate_proposal(proposal)
        if not validation.valid:
            approval.status = ApprovalStatus.CANCELLED
            self._action_service.update_status(
                approval.agent_action_id,
                ActionStatus.FAILED,
                error=f"Validation failed: {', '.join(validation.errors)}",
            )
            raise ValueError(f"Proposal validation failed: {validation.errors}")

        commit, warnings = self._configuration_service.apply_proposal_to_vcs(
            proposal, author=author, ref="HEAD"
        )
        approval.status = ApprovalStatus.APPROVED
        self._action_service.update_status(
            approval.agent_action_id,
            ActionStatus.COMPLETED,
            completed_at=now,
        )
        self._publish_resolved(approval, "approve", commit_hash=commit.hash)

        return approval, commit.hash, warnings

    def _publish_resolved(
            self,
            approval: AgentApprovalRequest,
            decision: str,
            commit_hash: Optional[str] = None,
    ) -> None:
        if self._event_bus:
            payload = approval.model_dump(mode="json")
            if commit_hash:
                payload["commit_hash"] = commit_hash
            self._event_bus.publish(
                AgentApprovalResolvedEvent(
                    approval_id=approval.id,
                    decision=decision,
                    approval_payload=payload,
                )
            )
