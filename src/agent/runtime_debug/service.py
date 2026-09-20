from __future__ import annotations

from typing import Any, List, Optional
from uuid import UUID

from src.agent.runtime_debug.graph import RuntimeDebugGraph
from src.agent.runtime_debug.models import (
    DebugDiagnosis,
    DebugSuggestion,
    ErrorSeverity,
    IncidentStatus,
    RuntimeIncident,
)
from src.agent.runtime_debug.tools import RuntimeDebugToolbox
from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.event_bus import EventBus
from src.core.interfaces.llm_adapter import LlmAdapter
from src.database.repositories.providers.postgres_runtime_incident_repository import (
    PostgresRuntimeIncidentRepository,
)
from src.events.runtime_events import DebugSuggestionCreatedEvent
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.vcs.application.service import VCSService


class RuntimeDebugService(ApplicationLoggingMixin):
    def __init__(
            self,
            database_manager: DatabaseManager,
            vcs: Optional[VCSService] = None,
            llm: Optional[LlmAdapter] = None,
            event_bus: Optional[EventBus] = None,
    ):
        self._database_manager = database_manager
        self._vcs = vcs
        self._llm = llm
        self._event_bus = event_bus
        self._toolbox = RuntimeDebugToolbox(database_manager=database_manager, vcs=vcs)
        self._graph = RuntimeDebugGraph(toolbox=self._toolbox, llm=llm).build()

    @property
    def graph(self):
        return self._graph

    def investigate_incident(self, incident_id: str) -> dict[str, Any]:
        self.app_logger.info(f"Starting investigation for incident: {incident_id}")
        self.set_incident_status(incident_id, IncidentStatus.INVESTIGATING)

        result = self._graph.invoke({"incident_id": incident_id})
        diagnosis: Optional[DebugDiagnosis] = result.get("diagnosis")
        suggestion: Optional[DebugSuggestion] = result.get("suggestion")

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

        return result

    def get_incident(self, incident_id: str) -> Optional[RuntimeIncident]:
        return self._toolbox.get_incident(incident_id)

    def list_incidents(
            self,
            status: Optional[IncidentStatus] = None,
            severity: Optional[ErrorSeverity] = None,
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
