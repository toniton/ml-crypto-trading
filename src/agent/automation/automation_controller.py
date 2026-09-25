from __future__ import annotations

import threading
from typing import Optional, Set

from src.agent.actions.executor import AgentActionExecutor
from src.agent.actions.models import (
    ActionReason,
    ActionSeverity,
    AgentAction,
    AgentActionType,
)
from src.agent.actions.safety import (
    ActionSafetyClass,
    DEFAULT_AUTOMATION_AUTHORITY,
    safety_class_for_action_type,
)
from src.agent.actions.service import AgentApprovalService
from src.agent.automation.automation_worker import AutomationWorker
from src.agent.automation.investigate_activity_anomaly import (
    AnomalyDecision,
    InvestigateActivityAnomaly,
)
from src.agent.monitoring.starvation_watchdog import StarvationWatchdog
from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.events.agent_event import AgentEvent
from src.events.agent_event_metadata import AgentEventMetadata
from src.events.agent_events import (
    AgentActionFailedEvent,
    AgentActionPlanRequestedEvent,
    AgentApprovalDecisionRequestedEvent,
    AgentApprovalResolvedEvent,
    TradingActivityAnomalyDetectedEvent,
    with_metadata,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class AutomationController(ApplicationLoggingMixin):
    def __init__(
            self,
            event_bus: EventBus,
            executor: AgentActionExecutor,
            approval_service: AgentApprovalService,
            investigation: InvestigateActivityAnomaly,
            watchdog: StarvationWatchdog,
            authority: Optional[Set[ActionSafetyClass]] = None,
    ):
        self._event_bus = event_bus
        self._executor = executor
        self._approval_service = approval_service
        self._investigation = investigation
        self._watchdog = watchdog
        self._authority = authority or DEFAULT_AUTOMATION_AUTHORITY
        self._worker = AutomationWorker(self._dispatch)
        self._subscriptions: list[str] = []
        self._processed: Set[str] = set()
        self._lock = threading.Lock()

    def start(self) -> None:
        self._subscribe()
        self._worker.start()
        self._watchdog.start()
        self.app_logger.info("Started agent automation controller")

    def stop(self) -> None:
        self._watchdog.stop()
        self._worker.stop()
        for subscription_id in self._subscriptions:
            self._event_bus.unsubscribe(subscription_id)
        self._subscriptions.clear()
        self.app_logger.info("Stopped agent automation controller")

    def _subscribe(self) -> None:
        for event_type in (
                "AgentActionPlanRequestedEvent",
                "AgentApprovalDecisionRequestedEvent",
                "TradingActivityAnomalyDetectedEvent",
        ):
            from src.events.message_event_bus import CallbackSubscription

            self._subscriptions.append(
                self._event_bus.subscribe(
                    event_type, CallbackSubscription(self._on_event)
                )
            )

    def _on_event(self, event: Event) -> None:
        # Trivial handler: hand off to the worker so bus subscribers never block.
        self._worker.submit(event)

    def _dispatch(self, event: Event) -> None:
        if isinstance(event, AgentActionPlanRequestedEvent):
            self._handle_action_plan(event)
        elif isinstance(event, AgentApprovalDecisionRequestedEvent):
            self._handle_approval_decision(event)
        elif isinstance(event, TradingActivityAnomalyDetectedEvent):
            self._handle_anomaly(event)

    def _handle_action_plan(self, event: AgentActionPlanRequestedEvent) -> None:
        if not self._mark_processed(event):
            return

        action_type = AgentActionType(event.action_type)
        safety_class = safety_class_for_action_type(action_type)
        if event.source != "user" and safety_class not in self._authority:
            self.app_logger.warning(
                f"Blocked {event.action_type} for {event.title}: {safety_class.value} "
                f"is not permitted by automation authority"
            )
            self._emit(
                AgentActionFailedEvent(
                    action_id=event.request_id or "",
                    error=f"Action class {safety_class.value} is not permitted for automation.",
                ),
                event,
            )
            return

        action = AgentAction(
            type=action_type,
            title=event.title,
            description=event.description,
            conversation_id=event.conversation_id,
            payload=event.payload or {},
            reason=ActionReason(**event.reason) if event.reason else None,
            severity=ActionSeverity(event.severity),
            requires_approval=event.requires_approval,
            request_id=str(event.request_id) if event.request_id else None,
            correlation_id=str(event.correlation_id),
            causation_id=str(event.causation_id) if event.causation_id else None,
        )
        self._executor.plan_and_execute(action)

    def _handle_approval_decision(self, event: AgentApprovalDecisionRequestedEvent) -> None:
        if not self._mark_processed(event):
            return
        try:
            self._approval_service.decide_approval(
                event.approval_id,
                event.decision,
                author=event.author,
                decision_notes=event.decision_notes,
            )
        except (ValueError, KeyError) as exc:
            self.app_logger.warning(
                f"Approval {event.approval_id} could not be resolved: {exc}"
            )
            error_code = "APPROVAL_CONFLICT" if isinstance(exc, ValueError) else "APPROVAL_NOT_FOUND"
            self._emit(
                AgentApprovalResolvedEvent(
                    approval_id=event.approval_id,
                    decision="error",
                    error_code=error_code,
                    error_message=str(exc),
                    approval_payload={
                        "approval_id": event.approval_id,
                        "error_code": error_code,
                        "error_message": str(exc),
                    },
                ),
                event,
            )

    def _handle_anomaly(self, event: TradingActivityAnomalyDetectedEvent) -> None:
        if not self._mark_processed(event):
            return
        decision = self._investigation.investigate(event)
        self._execute_decision(event, decision)

    def _execute_decision(
            self, event: TradingActivityAnomalyDetectedEvent, decision: AnomalyDecision
    ) -> None:
        if decision.kind == "proposal":
            action = self._build_action(
                AgentActionType.CREATE_PROPOSAL,
                event,
                title=f"Pause {decision.asset}",
                description="Proposal to pause a starved asset.",
                payload={
                    "proposed_change": decision.proposed_change or {},
                    "asset": decision.asset,
                },
                severity=ActionSeverity.WARNING,
            )
            if safety_class_for_action_type(AgentActionType.CREATE_PROPOSAL) in self._authority:
                self._executor.plan_and_execute(action)
            return

        action = self._build_action(
            AgentActionType.SEND_MESSAGE,
            event,
            title=f"Starvation diagnostic — {decision.asset}",
            description=decision.content,
            payload={"blocks": decision.blocks},
            severity=ActionSeverity.WARNING,
        )
        self._executor.plan_and_execute(action)

    def _build_action(
            self,
            action_type: AgentActionType,
            event: TradingActivityAnomalyDetectedEvent,
            title: str,
            description: str,
            payload: dict,
            severity: ActionSeverity,
    ) -> AgentAction:
        return AgentAction(
            type=action_type,
            title=title,
            description=description,
            conversation_id=None,
            payload=payload,
            reason=ActionReason(
                trigger="STARVATION_DETECTED",
                related_entities=[event.asset],
            ),
            severity=severity,
            correlation_id=str(event.correlation_id),
            causation_id=str(event.causation_id) if event.causation_id else event.event_id,
        )

    def _mark_processed(self, event: AgentEvent) -> bool:
        key = str(event.request_id) if event.request_id else event.event_id
        with self._lock:
            if key in self._processed:
                return False
            self._processed.add(key)
            return True

    def _emit(self, event: AgentEvent, source: AgentEvent) -> None:
        causation = source.request_id
        if causation is None and source.event_id:
            try:
                import uuid
                causation = uuid.UUID(source.event_id)
            except (ValueError, TypeError, AttributeError):
                causation = None
        metadata = AgentEventMetadata(
            request_id=source.request_id,
            correlation_id=source.correlation_id,
            causation_id=causation or source.causation_id,
        )
        with_metadata(event, metadata)
        self._event_bus.publish(event)