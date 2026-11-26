from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional
from uuid import UUID, uuid4

from src.agent.actions.models import (
    ActionReason,
    AgentAction,
    AgentActionType,
    AgentApprovalRequest,
)
from src.agent.actions.service import AgentActionService, AgentApprovalService
from src.agent.runtime_debug.graph import RuntimeDebugGraph
from src.agent.runtime_debug.models import (
    DebugDiagnosis,
    DebugSuggestion,
    IncidentStatus,
    RuntimeIncident,
)
from src.agent.runtime_debug.state import RuntimeDebugPresentation
from src.agent.runtime_debug.tools import RuntimeDebugToolbox
from src.core.interfaces.conversation_store import RESERVED_AGENT_SESSION_ID
from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.event_bus import EventBus
from src.core.interfaces.llm_adapter import LlmAdapter
from src.core.severity import Severity
from src.database.repositories.providers.postgres_runtime_incident_repository import (
    PostgresRuntimeIncidentRepository,
)
from src.events.agent_events import AgentMessageCreatedEvent
from src.events.runtime_events import DebugSuggestionCreatedEvent
from src.exchange.interfaces.exchange_rest_manager import ExchangeRestManager
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.vcs.application.service import VCSService


class RuntimeDebugService(ApplicationLoggingMixin):
    def __init__(
            self,
            database_manager: DatabaseManager,
            vcs: Optional[VCSService] = None,
            llm: Optional[LlmAdapter] = None,
            event_bus: Optional[EventBus] = None,
            rest_manager: Optional[ExchangeRestManager] = None,
            agent_event_bus: Optional[EventBus] = None,
            action_service: Optional[AgentActionService] = None,
            approval_service: Optional[AgentApprovalService] = None,
    ):
        self._database_manager = database_manager
        self._vcs = vcs
        self._llm = llm
        self._event_bus = event_bus
        self._rest_manager = rest_manager
        self._agent_event_bus = agent_event_bus
        self._action_service = action_service
        self._approval_service = approval_service
        self._toolbox = RuntimeDebugToolbox(
            database_manager=database_manager,
            vcs=vcs,
            rest_manager=rest_manager,
        )
        self._graph = RuntimeDebugGraph(toolbox=self._toolbox, llm=llm).build()

    @property
    def graph(self):
        return self._graph

    def set_llm(self, llm: Optional[LlmAdapter]) -> None:
        self._llm = llm
        self._graph = RuntimeDebugGraph(toolbox=self._toolbox, llm=llm).build()

    def set_agent_services(
            self,
            action_service: Optional[AgentActionService],
            approval_service: Optional[AgentApprovalService],
    ) -> None:
        self._action_service = action_service
        self._approval_service = approval_service

    def investigate_incident(self, incident_id: str) -> dict[str, Any]:
        self.app_logger.info(f"Starting investigation for incident: {incident_id}")
        self.set_incident_status(incident_id, IncidentStatus.INVESTIGATING)

        result = self._graph.invoke({"incident_id": incident_id})
        diagnosis: Optional[DebugDiagnosis] = result.get("diagnosis")
        suggestion: Optional[DebugSuggestion] = result.get("suggestion")
        presentation: Optional[RuntimeDebugPresentation] = result.get("presentation")
        incident: Optional[RuntimeIncident] = result.get("incident")

        if diagnosis or suggestion:
            with self._database_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresRuntimeIncidentRepository)
                if diagnosis:
                    repo.update_diagnosis(UUID(incident_id), diagnosis, diagnosis.confidence.value)
                if suggestion:
                    repo.update_suggestion(UUID(incident_id), suggestion, IncidentStatus.SUGGESTION_READY)

            if self._event_bus and suggestion:
                self._event_bus.publish(DebugSuggestionCreatedEvent(
                    incident_id=incident_id,
                    suggestion_payload=suggestion.to_dict(),
                ))

            if suggestion:
                self._notify_agent_session(
                    incident_id=incident_id,
                    incident=incident,
                    diagnosis=diagnosis,
                    suggestion=suggestion,
                    presentation=presentation,
                )

        return result

    def _notify_agent_session(
            self,
            incident_id: str,
            incident: Optional[RuntimeIncident],
            diagnosis: Optional[DebugDiagnosis],
            suggestion: DebugSuggestion,
            presentation: Optional[RuntimeDebugPresentation],
    ) -> None:
        blocks = list(presentation.blocks) if presentation and presentation.blocks else []
        content = (
            str(blocks[0].get("content"))
            if blocks and isinstance(blocks[0], dict) and blocks[0].get("content")
            else f"{diagnosis.summary if diagnosis else suggestion.summary}\n\n{suggestion.proposed_change}"
        )
        symbol = incident.asset if incident and incident.asset else "UNKNOWN"
        title = f"Order Validation Diagnostic — {symbol}" if symbol != "UNKNOWN" else "Runtime Incident Diagnostic"
        severity = incident.severity if incident else Severity.WARNING

        if self._action_service is not None:
            info_action = self._action_service.create_action(
                AgentAction(
                    type=AgentActionType.SEND_MESSAGE,
                    title=title,
                    description=suggestion.summary,
                    conversation_id=RESERVED_AGENT_SESSION_ID,
                    payload={"incident_id": incident_id, "asset": symbol},
                    reason=ActionReason(
                        trigger="RUNTIME_INCIDENT_INVESTIGATED",
                        evidence_ids=[incident_id],
                        related_entities=[symbol] if symbol != "UNKNOWN" else [],
                    ),
                    severity=severity,
                )
            )
            self._action_service.send_proactive_message(
                conversation_id=RESERVED_AGENT_SESSION_ID,
                message_id=f"incident-diag-{incident_id}-{uuid4().hex[:8]}",
                content=content,
                blocks=blocks or [{"type": "markdown", "content": content}],
                action=info_action,
                force=True,
            )
        elif self._agent_event_bus is not None:
            self._agent_event_bus.publish(
                AgentMessageCreatedEvent(
                    conversation_id=RESERVED_AGENT_SESSION_ID,
                    message_payload={
                        "message_id": f"incident-diag-{incident_id}-{uuid4().hex[:8]}",
                        "content": content,
                        "blocks": blocks or [{"type": "markdown", "content": content}],
                        "payload": {
                            "blocks": blocks or [{"type": "markdown", "content": content}],
                            "notification": {
                                "title": title,
                                "preview": suggestion.summary[:140],
                                "severity": severity.value,
                            },
                        },
                    },
                )
            )

        self._maybe_request_min_quantity_approval(
            incident_id=incident_id,
            incident=incident,
            suggestion=suggestion,
        )

    def _maybe_request_min_quantity_approval(
            self,
            incident_id: str,
            incident: Optional[RuntimeIncident],
            suggestion: DebugSuggestion,
    ) -> None:
        if (
            not suggestion.requires_configuration_change
            or self._approval_service is None
            or self._action_service is None
            or self._vcs is None
        ):
            return
        if not suggestion.affected_component.startswith("assets.") or not suggestion.affected_component.endswith(".min_quantity"):
            return

        size_evidence = next(
            (e for e in suggestion.evidence if e.data.get("recommended_min_quantity") is not None),
            None,
        )
        if size_evidence is None:
            return

        raw_recommended = str(size_evidence.data["recommended_min_quantity"])
        try:
            new_value = float(Decimal(raw_recommended))
        except (InvalidOperation, ValueError):
            return

        symbol = (
            (incident.asset if incident and incident.asset else None)
            or size_evidence.data.get("symbol")
            or suggestion.affected_component.split(".")[1]
        )
        config_path = f"assets.{symbol}.min_quantity"

        try:
            base_commit = self._vcs.head("HEAD").hash
            current_config = self._vcs.checkout(base_commit)
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.warning(
                "Unable to read VCS HEAD for min_quantity approval proposal on %s: %s",
                symbol,
                exc,
            )
            return

        old_value = self._extract_current_min_quantity(current_config, symbol)
        proposed_change = {
            "changes": [
                {
                    "path": config_path,
                    "old_value": old_value,
                    "new_value": new_value,
                    "reason": suggestion.rationale,
                }
            ],
            "risks": [
                f"Minimum order size for {symbol} will increase to {raw_recommended}.",
            ],
            "expected_effect": suggestion.proposed_change,
        }

        proposal_action = self._action_service.create_action(
            AgentAction(
                type=AgentActionType.REQUEST_APPROVAL,
                title=f"Update {config_path} to {raw_recommended}",
                description=suggestion.proposed_change,
                conversation_id=RESERVED_AGENT_SESSION_ID,
                payload={"incident_id": incident_id, "asset": symbol, "path": config_path},
                reason=ActionReason(
                    trigger="ORDER_VALIDATION_BELOW_MIN_ORDER_SIZE",
                    evidence_ids=[incident_id],
                    related_entities=[symbol],
                ),
                severity=Severity.WARNING,
                requires_approval=True,
            )
        )
        approval_request = AgentApprovalRequest(
            conversation_id=RESERVED_AGENT_SESSION_ID,
            agent_action_id=proposal_action.id,
            action_type=AgentActionType.CREATE_PROPOSAL,
            title=f"Update {config_path} to {raw_recommended}",
            description=suggestion.rationale,
            proposed_change=proposed_change,
            base_commit=base_commit,
            asset=symbol,
        )
        self._approval_service.request_approval(approval_request)

    @staticmethod
    def _extract_current_min_quantity(config: Any, symbol: str) -> Any:
        if not isinstance(config, dict):
            return None
        assets = config.get("assets")
        if isinstance(assets, dict):
            entry = assets.get(symbol)
            if isinstance(entry, dict):
                return entry.get("min_quantity")
        elif isinstance(assets, list):
            for entry in assets:
                if isinstance(entry, dict) and entry.get("ticker_symbol") == symbol:
                    return entry.get("min_quantity")
        return None

    def get_incident(self, incident_id: str) -> Optional[RuntimeIncident]:
        return self._toolbox.get_incident(incident_id)

    def list_incidents(
            self,
            status: Optional[IncidentStatus] = None,
            severity: Optional[Severity] = None,
            asset: Optional[str] = None,
            exchange: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> List[RuntimeIncident]:
        with self._database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresRuntimeIncidentRepository)
            return repo.list_incidents(
                status=status,
                severity=severity,
                asset=asset,
                exchange=exchange,
                limit=limit,
                offset=offset,
            )

    def list_active_incidents(self) -> List[RuntimeIncident]:
        with self._database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresRuntimeIncidentRepository)
            return repo.list_active_incidents()

    def set_incident_status(self, incident_id: str, status: IncidentStatus, notes: Optional[str] = None) -> None:
        with self._database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresRuntimeIncidentRepository)
            repo.update_status(UUID(incident_id), status=status, notes=notes)
