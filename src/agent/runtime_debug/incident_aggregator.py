from __future__ import annotations

from typing import Any, Callable, Optional
from uuid import uuid4

from src.agent.runtime_debug.fingerprint import compute_error_fingerprint
from src.agent.runtime_debug.models import (
    ErrorCategory,
    ErrorSeverity,
    IncidentStatus,
    RuntimeErrorEvent,
    RuntimeIncident,
)
from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.database.repositories.providers.postgres_runtime_incident_repository import (
    PostgresRuntimeIncidentRepository,
)
from src.events.runtime_events import (
    RuntimeIncidentCreatedEvent,
    RuntimeIncidentUpdatedEvent,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class IncidentAggregator(ApplicationLoggingMixin):
    ACTIVE_STATUSES = [
        IncidentStatus.DETECTED,
        IncidentStatus.INVESTIGATING,
        IncidentStatus.DIAGNOSED,
        IncidentStatus.SUGGESTION_READY,
        IncidentStatus.ACKNOWLEDGED,
    ]

    def __init__(
            self,
            database_manager: DatabaseManager,
            event_bus: Optional[EventBus] = None,
            investigation_callback: Optional[Callable[[str], Any]] = None,
            auto_investigate: bool = True,
    ):
        self._database_manager = database_manager
        self._event_bus = event_bus
        self._investigation_callback = investigation_callback
        self._auto_investigate = auto_investigate
        self._subscription_id: Optional[str] = None

    def subscribe(self, event_bus: EventBus) -> str:
        self._event_bus = event_bus
        from src.events.message_event_bus import CallbackSubscription
        self._subscription_id = event_bus.subscribe(
            "RuntimeErrorCapturedEvent",
            CallbackSubscription(self._on_error_captured_event),
        )
        return self._subscription_id

    def _on_error_captured_event(self, event: Event) -> None:
        payload = getattr(event, "event_payload", None)
        if isinstance(payload, dict):
            error_event = RuntimeErrorEvent.from_dict(payload)
            self.process_error_event(error_event)

    @classmethod
    def classify_error(cls, event: RuntimeErrorEvent) -> tuple[ErrorCategory, ErrorSeverity]:
        msg = (event.message or "").lower()
        http_status = event.http_status
        exchange_code = event.exchange_code

        if http_status == 429 or "rate limit" in msg:
            return ErrorCategory.RATE_LIMIT, ErrorSeverity.WARNING

        if http_status in (401, 403) or "unauthorized" in msg or "authentication" in msg:
            return ErrorCategory.AUTHENTICATION, ErrorSeverity.CRITICAL

        if http_status in (502, 503, 504) or "timeout" in msg or "connection refused" in msg or "url error" in msg:
            return ErrorCategory.TRANSIENT_NETWORK, ErrorSeverity.WARNING

        if (
            http_status == 400
            or exchange_code is not None
            or "invalid quantity" in msg
            or "precision" in msg
            or "min_quantity" in msg
            or "insufficient balance" in msg
        ):
            return ErrorCategory.EXCHANGE_VALIDATION, ErrorSeverity.CRITICAL

        if "config" in (event.component or "").lower() or "configuration" in msg:
            return ErrorCategory.CONFIGURATION, ErrorSeverity.ERROR

        if "database" in msg or "sqlalchemy" in msg or "postgres" in msg:
            return ErrorCategory.DATABASE, ErrorSeverity.CRITICAL

        return ErrorCategory.UNKNOWN, event.severity or ErrorSeverity.ERROR

    def process_error_event(self, event: RuntimeErrorEvent) -> RuntimeIncident:
        if not event.fingerprint:
            event.fingerprint = compute_error_fingerprint(event)

        category, severity = self.classify_error(event)
        event.severity = severity

        should_trigger_investigation = False
        incident_id_to_investigate: Optional[str] = None

        with self._database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresRuntimeIncidentRepository)
            active_incident = repo.get_by_fingerprint(
                event.fingerprint, status_filter=self.ACTIVE_STATUSES
            )

            if active_incident:
                active_incident.occurrence_count += 1
                active_incident.last_seen = event.timestamp
                event.incident_id = active_incident.id
                repo.update(str(active_incident.id), active_incident)
                repo.add_error_event(event)
                incident = active_incident

                if self._event_bus:
                    self._event_bus.publish(RuntimeIncidentUpdatedEvent(
                        incident_payload=active_incident.to_dict()
                    ))
            else:
                incident = RuntimeIncident(
                    id=uuid4(),
                    fingerprint=event.fingerprint,
                    status=IncidentStatus.DETECTED,
                    category=category,
                    severity=severity,
                    component=event.component,
                    operation=event.operation,
                    asset=event.asset,
                    exchange=event.exchange,
                    commit_hash=event.commit_hash,
                    first_seen=event.timestamp,
                    last_seen=event.timestamp,
                    occurrence_count=1,
                    error_events=[event.id],
                )
                event.incident_id = incident.id
                repo.save(incident)
                repo.add_error_event(event)

                if self._event_bus:
                    self._event_bus.publish(RuntimeIncidentCreatedEvent(
                        incident_payload=incident.to_dict()
                    ))

                if self._auto_investigate and (
                    category == ErrorCategory.EXCHANGE_VALIDATION
                    or severity == ErrorSeverity.CRITICAL
                ):
                    should_trigger_investigation = True
                    incident_id_to_investigate = str(incident.id)

        if should_trigger_investigation and self._investigation_callback and incident_id_to_investigate:
            try:
                self._investigation_callback(incident_id_to_investigate)
            except Exception as exc:
                self.app_logger.warning(
                    f"Failed to auto-trigger investigation for incident {incident_id_to_investigate}: {exc}"
                )

        return incident
