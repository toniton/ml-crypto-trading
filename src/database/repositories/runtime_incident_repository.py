from __future__ import annotations

import abc
from typing import List, Optional
from uuid import UUID

from src.agent.runtime_debug.models import (
    DebugDiagnosis,
    DebugSuggestion,
    ErrorSeverity,
    IncidentStatus,
    RuntimeErrorEvent,
    RuntimeIncident,
)
from src.database.repositories.base_repository import BaseRepository


class RuntimeIncidentRepository(BaseRepository[RuntimeIncident], metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def get_by_fingerprint(self, fingerprint: str, status_filter: Optional[List[IncidentStatus]] = None) -> Optional[RuntimeIncident]:
        raise NotImplementedError()

    @abc.abstractmethod
    def list_incidents(
            self,
            status: Optional[IncidentStatus] = None,
            severity: Optional[ErrorSeverity] = None,
            asset: Optional[str] = None,
            exchange: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> List[RuntimeIncident]:
        raise NotImplementedError()

    @abc.abstractmethod
    def list_active_incidents(self) -> List[RuntimeIncident]:
        raise NotImplementedError()

    @abc.abstractmethod
    def add_error_event(self, event: RuntimeErrorEvent) -> RuntimeErrorEvent:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_error_events(self, incident_id: UUID, limit: int = 100) -> List[RuntimeErrorEvent]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_recent_error_events(
            self,
            asset: Optional[str] = None,
            exchange: Optional[str] = None,
            limit: int = 20,
    ) -> List[RuntimeErrorEvent]:
        raise NotImplementedError()

    @abc.abstractmethod
    def update_diagnosis(self, incident_id: UUID, diagnosis: DebugDiagnosis, confidence: str) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def update_suggestion(self, incident_id: UUID, suggestion: DebugSuggestion, status: IncidentStatus) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def update_status(self, incident_id: UUID, status: IncidentStatus, notes: Optional[str] = None) -> None:
        raise NotImplementedError()
