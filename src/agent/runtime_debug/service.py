from __future__ import annotations

from decimal import Decimal, InvalidOperation
import time
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
        self._last_swept_at: dict[str, float] = {}

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
                approval_request = self._notify_agent_session(
                    incident_id=incident_id,
                    incident=incident,
                    diagnosis=diagnosis,
                    suggestion=suggestion,
                    presentation=presentation,
                )
                if approval_request is not None:
                    result["approval_request"] = approval_request

        return result

    def _notify_agent_session(
            self,
            incident_id: str,
            incident: Optional[RuntimeIncident],
            diagnosis: Optional[DebugDiagnosis],
            suggestion: DebugSuggestion,
            presentation: Optional[RuntimeDebugPresentation],
    ) -> Optional[AgentApprovalRequest]:
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

        return self._maybe_request_config_approval(
            incident_id=incident_id,
            incident=incident,
            suggestion=suggestion,
        )

    def _find_pending_config_approval(
            self,
            symbol: str,
            config_path: str,
    ) -> Optional[AgentApprovalRequest]:
        if self._approval_service is None:
            return None
        for pending in self._approval_service.list_pending_approvals():
            if pending.asset and pending.asset.upper() != symbol.upper():
                continue
            changes = (pending.proposed_change or {}).get("changes") or []
            if any(isinstance(c, dict) and c.get("path") == config_path for c in changes):
                return pending
        return None

    def _resolve_candidate_config_changes(
            self,
            incident: Optional[RuntimeIncident],
            suggestion: DebugSuggestion,
    ) -> tuple[str, list[dict[str, Any]], str]:
        """Extract (symbol, raw_changes, trigger_name) from structured suggestion evidence."""
        balance_evidence = next(
            (e for e in suggestion.evidence if e.source == "balance_analysis" and e.data.get("proposed_changes")),
            None,
        )
        if balance_evidence is not None:
            symbol = str(
                balance_evidence.data.get("symbol")
                or (incident.asset if incident and incident.asset else None)
                or (suggestion.affected_component.split(".")[1] if suggestion.affected_component.startswith("assets.") else "UNKNOWN")
            )
            return symbol, list(balance_evidence.data["proposed_changes"]), "INSUFFICIENT_AVAILABLE_BALANCE"

        if (
            suggestion.affected_component.startswith("assets.")
            and suggestion.affected_component.endswith(".min_quantity")
        ):
            size_evidence = next(
                (e for e in suggestion.evidence if e.data.get("recommended_min_quantity") is not None),
                None,
            )
            if size_evidence is not None:
                raw_recommended = str(size_evidence.data["recommended_min_quantity"])
                try:
                    new_value = float(Decimal(raw_recommended))
                except (InvalidOperation, ValueError):
                    return "", [], ""
                symbol = str(
                    (incident.asset if incident and incident.asset else None)
                    or size_evidence.data.get("symbol")
                    or suggestion.affected_component.split(".")[1]
                )
                return (
                    symbol,
                    [
                        {
                            "path": f"assets.{symbol}.min_quantity",
                            "new_value": new_value,
                            "reason": suggestion.rationale,
                        }
                    ],
                    "ORDER_VALIDATION_BELOW_MIN_ORDER_SIZE",
                )

        return "", [], ""

    def _maybe_request_config_approval(
            self,
            incident_id: str,
            incident: Optional[RuntimeIncident],
            suggestion: DebugSuggestion,
    ) -> Optional[AgentApprovalRequest]:
        if (
            not suggestion.requires_configuration_change
            or self._approval_service is None
            or self._action_service is None
            or self._vcs is None
        ):
            return None

        symbol, raw_changes, trigger_name = self._resolve_candidate_config_changes(incident, suggestion)
        if not symbol or not raw_changes:
            return None

        primary_path = str(raw_changes[0]["path"])
        existing_pending = self._find_pending_config_approval(symbol, primary_path)
        if existing_pending is not None:
            self.app_logger.info(
                "Skipping duplicate approval for %s (%s); pending approval %s already exists",
                primary_path,
                incident_id,
                existing_pending.id,
            )
            return existing_pending

        try:
            base_commit = self._vcs.head("HEAD").hash
            current_config = self._vcs.checkout(base_commit)
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.warning(
                "Unable to read VCS HEAD for config approval proposal on %s: %s",
                symbol,
                exc,
            )
            return None

        changes: list[dict[str, Any]] = []
        for item in raw_changes:
            path = str(item["path"])
            new_value = item["new_value"]
            old_value = self._extract_config_path_value(current_config, path)
            if path.endswith(".min_quantity") and old_value is not None:
                try:
                    if Decimal(str(old_value)) >= Decimal(str(new_value)):
                        continue
                except InvalidOperation:
                    pass
            elif old_value is not None and old_value == new_value:
                continue
            changes.append(
                {
                    "path": path,
                    "old_value": old_value,
                    "new_value": new_value,
                    "reason": str(item.get("reason") or suggestion.rationale),
                }
            )

        if not changes:
            self.app_logger.info(
                "Skipping no-op config proposal for %s (%s): VCS HEAD already satisfies target values",
                symbol,
                incident_id,
            )
            return None

        primary_change = changes[0]
        title = f"Update {primary_change['path']} to {primary_change['new_value']}"
        proposed_change = {
            "changes": changes,
            "risks": [
                f"Configuration path {primary_change['path']} will change from "
                f"{primary_change['old_value']} to {primary_change['new_value']}."
            ],
            "expected_effect": suggestion.proposed_change,
        }

        proposal_action = self._action_service.create_action(
            AgentAction(
                type=AgentActionType.REQUEST_APPROVAL,
                title=title,
                description=suggestion.proposed_change,
                conversation_id=RESERVED_AGENT_SESSION_ID,
                payload={"incident_id": incident_id, "asset": symbol, "path": primary_change["path"]},
                reason=ActionReason(
                    trigger=trigger_name,
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
            title=title,
            description=suggestion.rationale,
            proposed_change=proposed_change,
            base_commit=base_commit,
            asset=symbol,
        )
        return self._approval_service.request_approval(approval_request)

    @classmethod
    def _extract_config_path_value(cls, config: Any, path: str) -> Any:
        if not isinstance(config, dict) or not path:
            return None
        parts = path.split(".")
        if len(parts) >= 3 and parts[0] == "assets":
            symbol = parts[1]
            asset_entry = cls._find_asset_entry(config, symbol)
            if asset_entry is None:
                return None
            current: Any = asset_entry
            for key in parts[2:]:
                if isinstance(current, dict):
                    current = current.get(key)
                else:
                    return None
            return current
        current = config
        for key in parts:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    @staticmethod
    def _find_asset_entry(config: dict[str, Any], symbol: str) -> Optional[dict[str, Any]]:
        assets = config.get("assets")
        if isinstance(assets, dict):
            entry = assets.get(symbol)
            return entry if isinstance(entry, dict) else None
        if isinstance(assets, list):
            for entry in assets:
                if not isinstance(entry, dict):
                    continue
                if entry.get("ticker_symbol") == symbol:
                    return entry
                base = entry.get("base_ticker_symbol")
                quote = entry.get("quote_ticker_symbol")
                sep = entry.get("separator") if entry.get("separator") is not None else "_"
                if base and quote and f"{base}{sep}{quote}".upper() == symbol.upper():
                    return entry
        return None

    def get_exchange_constraints(self, exchange: str, ticker_symbol: str) -> dict[str, Any]:
        """Fetch live exchange instrument constraints alongside current VCS min_quantity."""
        normalized_symbol = ticker_symbol.upper().replace("/", "_").replace("-", "_")
        rules = self._toolbox.get_exchange_instrument_metadata(exchange, normalized_symbol)
        current_min_quantity = None
        if self._vcs is not None:
            try:
                head_hash = self._vcs.head("HEAD").hash
                current_config = self._vcs.checkout(head_hash)
                current_min_quantity = self._extract_current_min_quantity(
                    current_config, normalized_symbol
                )
            except Exception as exc:  # pylint: disable=broad-except
                self.app_logger.warning(
                    "Unable to read current min_quantity from VCS HEAD for %s: %s",
                    normalized_symbol,
                    exc,
                )
        return {
            **rules,
            "current_min_quantity": current_min_quantity,
        }

    def sweep_critical_incidents(self, cooldown_seconds: float = 3600.0) -> list[str]:
        """Pick up active CRITICAL incidents lacking an actionable configuration proposal."""
        now = time.monotonic()
        investigated: list[str] = []
        active = self.list_active_incidents()
        for incident in active:
            if incident.severity != Severity.CRITICAL:
                continue
            if incident.status not in (
                IncidentStatus.DETECTED,
                IncidentStatus.ACKNOWLEDGED,
                IncidentStatus.DIAGNOSED,
            ):
                continue
            inc_id = str(incident.id)
            last_swept = self._last_swept_at.get(inc_id)
            if last_swept is not None and (now - last_swept) < cooldown_seconds:
                continue
            needs_investigation = incident.suggestion is None or (
                not incident.suggestion.requires_configuration_change
                and incident.category.value == "EXCHANGE_VALIDATION"
            )
            if not needs_investigation:
                continue
            self._last_swept_at[inc_id] = now
            try:
                self.investigate_incident(inc_id)
                investigated.append(inc_id)
            except Exception as exc:  # pylint: disable=broad-except
                self.app_logger.warning(
                    "Critical incident sweep failed for %s: %s", inc_id, exc
                )
        return investigated

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
                if not isinstance(entry, dict):
                    continue
                if entry.get("ticker_symbol") == symbol:
                    return entry.get("min_quantity")
                base = entry.get("base_ticker_symbol")
                quote = entry.get("quote_ticker_symbol")
                sep = entry.get("separator") if entry.get("separator") is not None else "_"
                if base and quote and f"{base}{sep}{quote}".upper() == symbol.upper():
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
