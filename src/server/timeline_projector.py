from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.agent.oracle.events import OracleSummaryEvent
from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.database.dao.runtime_incident_dao import RuntimeIncidentDao
from src.database.repositories.providers.postgres_timeline_repository import PostgresTimelineRepository
from src.database.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.events.agent_events import (
    AgentActionCompletedEvent,
    AgentActionCreatedEvent,
    AgentActionFailedEvent,
    AgentApprovalRequestedEvent,
    AgentApprovalResolvedEvent,
    TradingActivityAnomalyDetectedEvent,
)
from src.events.decision_models import (
    AgentDecisionRecordedEvent,
    EntityRef,
)
from src.events.message_event_bus import CallbackSubscription
from src.events.runtime_events import (
    RuntimeErrorCapturedEvent,
    RuntimeIncidentCreatedEvent,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.timeline.timeline_models import TimelineCategory, TimelineItem
from src.trading.events import ConsensusEvaluatedEvent
from src.trading.events.domain_events import (
    ReconciliationDiscrepancyEvent,
    TradingDecisionCreatedEvent,
)
from src.trading.helpers.format_helper import FormatHelper
from src.vcs.application.events import RefChangedEvent


class TimelineProjector(ApplicationLoggingMixin):
    """Projects significant domain events into indexable TimelineItem read models."""

    EVENT_CLASSES: tuple[type[Event], ...] = (
        ConsensusEvaluatedEvent,
        TradingDecisionCreatedEvent,
        TradingActivityAnomalyDetectedEvent,
        AgentDecisionRecordedEvent,
        AgentActionCreatedEvent,
        AgentActionCompletedEvent,
        AgentActionFailedEvent,
        AgentApprovalRequestedEvent,
        AgentApprovalResolvedEvent,
        OracleSummaryEvent,
        RefChangedEvent,
        RuntimeErrorCapturedEvent,
        RuntimeIncidentCreatedEvent,
        ReconciliationDiscrepancyEvent,
    )

    @classmethod
    def _event_names_for(cls, event_cls: type[Event]) -> set[str]:
        names = {event_cls.__name__}
        if event_cls.EVENT_TYPE:
            names.add(event_cls.EVENT_TYPE)
        return names

    @classmethod
    def _derive_event_types(cls) -> tuple[str, ...]:
        return tuple(
            name
            for event_cls in cls.EVENT_CLASSES
            for name in cls._event_names_for(event_cls)
        )

    def __init__(
            self,
            event_bus: EventBus,
            max_items: int = 2000,
            db_manager: Optional[DatabaseManager] = None,
            flush_interval_seconds: float = 30.0,
    ):
        self._event_bus = event_bus
        self._max_items = max_items
        self._db_manager = db_manager
        self._flush_interval_seconds = flush_interval_seconds
        self._items: list[TimelineItem] = []
        self._unpersisted_items: list[TimelineItem] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._flush_thread: Optional[threading.Thread] = None
        self._subscriptions: list[str] = []
        if self._db_manager:
            self._hydrate_from_db()
            if self._flush_interval_seconds > 0:
                self._start_flush_thread()

    def _start_flush_thread(self) -> None:
        self._flush_thread = threading.Thread(
            target=self._run_flush_loop,
            daemon=True,
            name="TimelineProjectorFlush",
        )
        self._flush_thread.start()

    def _run_flush_loop(self) -> None:
        while not self._stop_event.wait(self._flush_interval_seconds):
            self.flush()

    def flush(self) -> None:
        if not self._db_manager:
            return
        with self._lock:
            if not self._unpersisted_items:
                return
            items_to_flush = list(self._unpersisted_items)
            self._unpersisted_items.clear()

        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresTimelineRepository)
                repo.save_batch(items_to_flush)
        except Exception as err:
            self.app_logger.warning(f"Failed to flush timeline items to database: {err}")
            with self._lock:
                self._unpersisted_items = items_to_flush + self._unpersisted_items

    def _hydrate_from_db(self) -> None:
        if not self._db_manager:
            return
        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresTimelineRepository)
                persisted = repo.list_items(limit=self._max_items)
                if persisted:
                    with self._lock:
                        self._items = list(reversed(persisted))
                    return

                if not isinstance(uow, SqlAlchemyUnitOfWork):
                    return

                session = uow.session
                incidents = (
                    session.query(RuntimeIncidentDao)
                    .order_by(RuntimeIncidentDao.first_seen.asc())
                    .limit(200)
                    .all()
                )
                for inc in incidents:
                    seen_dt = inc.first_seen
                    if seen_dt:
                        if seen_dt.tzinfo is None:
                            seen_dt = seen_dt.replace(tzinfo=timezone.utc)
                        self._items.append(
                            TimelineItem(
                                timestamp=seen_dt.isoformat(),
                                category=TimelineCategory.RUNTIME,
                                severity=inc.severity.upper() if inc.severity else "ERROR",
                                title=f"Runtime Incident: {inc.id[:8] if inc.id else ''}",
                                summary=inc.notes or f"Incident in {inc.component}: {inc.category}",
                                correlation_id=None,
                                causation_id=None,
                                actor_type="WATCHDOG",
                                primary_entity=EntityRef(type="ASSET", id=inc.asset) if inc.asset else None,
                                entities=[EntityRef(type="INCIDENT", id=inc.id)] if inc.id else [],
                                metadata={"incident_id": inc.id, "component": inc.component},
                            )
                        )

                self._items.sort(key=lambda x: x.timestamp)
        except Exception as err:
            self.app_logger.warning(f"Failed to hydrate timeline from database: {err}")

    def subscribe(self) -> None:
        callback_sub = CallbackSubscription(self._on_event)
        for event_type in self._derive_event_types():
            self._subscriptions.append(
                self._event_bus.subscribe(event_type, callback_sub)
            )

    def close(self) -> None:
        self._stop_event.set()
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=2.0)
        for sub_id in self._subscriptions:
            try:
                self._event_bus.unsubscribe(sub_id)
            except Exception:
                pass
        self._subscriptions.clear()
        self.flush()

    def _on_event(self, event: Event) -> None:
        item = self._project_event(event)
        if item is not None:
            self._append_item(item)

    def _append_item(self, item: TimelineItem) -> None:
        should_flush_evicted = False
        with self._lock:
            self._items.append(item)
            if self._db_manager:
                self._unpersisted_items.append(item)
            if len(self._items) > self._max_items:
                self._items.pop(0)
                should_flush_evicted = True

        if should_flush_evicted:
            self.flush()

    # pylint: disable=too-many-return-statements,too-many-branches
    def _project_event(self, event: Event) -> Optional[TimelineItem]:
        if isinstance(event, ConsensusEvaluatedEvent):
            return self._project_consensus(event)
        if isinstance(event, TradingDecisionCreatedEvent):
            return self._project_trading_decision(event)
        if isinstance(event, TradingActivityAnomalyDetectedEvent):
            return self._project_anomaly(event)
        if isinstance(event, AgentDecisionRecordedEvent):
            return self._project_decision_recorded(event)
        if isinstance(event, AgentApprovalRequestedEvent):
            return self._project_approval_requested(event)
        if isinstance(event, AgentApprovalResolvedEvent):
            return self._project_approval_resolved(event)
        if isinstance(event, AgentActionCreatedEvent):
            return self._project_action_created(event)
        if isinstance(event, AgentActionCompletedEvent):
            return self._project_action_completed(event)
        if isinstance(event, AgentActionFailedEvent):
            return self._project_action_failed(event)
        if isinstance(event, OracleSummaryEvent):
            return self._project_oracle_summary(event)
        if isinstance(event, RefChangedEvent):
            return self._project_vcs(event)
        if isinstance(event, RuntimeErrorCapturedEvent):
            return self._project_runtime_error(event)
        if isinstance(event, RuntimeIncidentCreatedEvent):
            return self._project_runtime_incident(event)
        if isinstance(event, ReconciliationDiscrepancyEvent):
            return self._project_reconciliation_discrepancy(event)
        return None

    @staticmethod
    def _project_trading_decision(event: TradingDecisionCreatedEvent) -> TimelineItem:
        decision = event.decision
        symbol = event.symbol or (decision.ticker_symbol if decision is not None else "")
        action = event.action or (decision.trade_action.value if decision is not None else "")
        status = event.status or (decision.status.value if decision is not None else "")
        entities = []
        if symbol:
            entities.append(EntityRef(type="ASSET", id=symbol))
        if decision is not None and decision.resulting_order_id:
            entities.append(EntityRef(type="ORDER", id=decision.resulting_order_id))

        severity = "INFO" if status == "EXECUTED" else ("WARNING" if status == "REJECTED" else "INFO")
        title = f"Trading Decision: {action} {symbol} ({status})"

        if status == "EXECUTED":
            qty_str = f"qty: {decision.sizing_snapshot.final_quantity}" if decision is not None and decision.sizing_snapshot and decision.sizing_snapshot.final_quantity else ""
            regime_str = f"regime: {decision.regime_snapshot.regime}" if decision is not None and decision.regime_snapshot else ""
            summary = f"Decision executed: {action} {symbol} ({qty_str}, {regime_str})"
        elif status == "REJECTED":
            reason = decision.rejection_reason if decision is not None else ""
            summary = f"Decision rejected: {action} {symbol} - {reason}"
        else:
            summary = f"Decision skipped: {action} {symbol}"

        return TimelineItem(
            timestamp=datetime.fromtimestamp(decision.timestamp, tz=timezone.utc).isoformat() if decision is not None else datetime.now(timezone.utc).isoformat(),
            category=TimelineCategory.DECISION,
            severity=severity,
            title=title,
            summary=summary,
            correlation_id=decision.decision_id if decision is not None else None,
            causation_id=decision.commit_hash if decision is not None else None,
            actor_type="ENGINE",
            primary_entity=EntityRef(type="ASSET", id=symbol) if symbol else None,
            entities=entities,
            metadata=decision.to_dict() if decision is not None else {},
        )

    @staticmethod
    def _project_reconciliation_discrepancy(event: ReconciliationDiscrepancyEvent) -> TimelineItem:
        entities = []
        if event.asset_or_currency:
            entities.append(EntityRef(type="ASSET", id=event.asset_or_currency))
        if event.exchange:
            entities.append(EntityRef(type="EXCHANGE", id=event.exchange))

        diff_str = f" Diff: {event.difference:+}" if event.difference is not None else ""
        summary = (
            f"{event.discrepancy_type} on {event.exchange} for {event.asset_or_currency}. "
            f"Local: {event.local_value}, Exchange: {event.exchange_value}.{diff_str} Action: {event.action_taken}"
        )
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.RUNTIME,
            severity=event.severity.upper() if event.severity else "CRITICAL",
            title=f"Reconciliation: {event.discrepancy_type} ({event.asset_or_currency})",
            summary=summary,
            correlation_id=str(event.correlation_id) if event.correlation_id else None,
            causation_id=str(event.causation_id) if event.causation_id else None,
            actor_type="SYSTEM",
            primary_entity=EntityRef(type="ASSET", id=event.asset_or_currency) if event.asset_or_currency else None,
            entities=entities,
            metadata={
                "discrepancy_type": event.discrepancy_type,
                "exchange": event.exchange,
                "asset_or_currency": event.asset_or_currency,
                "local_value": str(event.local_value),
                "exchange_value": str(event.exchange_value),
                "difference": str(event.difference) if event.difference is not None else None,
                "action_taken": event.action_taken,
                "details": event.details,
            },
        )

    def _project_consensus(self, event: ConsensusEvaluatedEvent) -> TimelineItem:
        symbol = event.symbol
        decision = event.decision
        quorum_met = event.quorum_met
        buy_votes = event.buy_votes
        sell_votes = event.sell_votes
        entities = [EntityRef(type="ASSET", id=symbol)] if symbol else []
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.DECISION,
            severity="INFO",
            title=f"Consensus Evaluated: {symbol} -> {decision}",
            summary=f"Consensus {decision} (Quorum: {quorum_met}, Buy: {buy_votes}, Sell: {sell_votes})",
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            actor_type=event.actor_type,
            primary_entity=EntityRef(type="ASSET", id=symbol) if symbol else None,
            entities=entities,
            metadata={
                "decision": decision,
                "quorum_met": quorum_met,
                "buy_votes": buy_votes,
                "sell_votes": sell_votes,
            },
        )

    def _project_anomaly(self, event: TradingActivityAnomalyDetectedEvent) -> TimelineItem:
        asset = event.asset
        anomaly_kind = event.anomaly_kind
        threshold = event.threshold
        entities = [EntityRef(type="ASSET", id=asset)] if asset else []
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.AGENT,
            severity="WARNING",
            title=f"Trading Starvation Detected: {asset}",
            summary=f"Watchdog detected {anomaly_kind} beyond {threshold:.0f}s threshold",
            correlation_id=str(event.correlation_id) if event.correlation_id else None,
            causation_id=str(event.causation_id) if event.causation_id else None,
            actor_type="WATCHDOG",
            primary_entity=EntityRef(type="ASSET", id=asset) if asset else None,
            entities=entities,
            metadata={"asset": asset, "anomaly_kind": anomaly_kind, "threshold": threshold},
        )

    def _project_decision_recorded(self, event: AgentDecisionRecordedEvent) -> TimelineItem:
        decision = event.decision
        summary = decision.summary if decision else ""
        rationale = decision.rationale if decision else ""
        entities = decision.entities if decision else []
        actor_type = decision.actor_type.value if decision else "AGENT"
        primary_entity = entities[0] if entities else None
        metadata = decision.to_dict() if decision else {}
        if decision and decision.parameters:
            metadata.update(decision.parameters)
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.DECISION,
            severity="INFO",
            title=f"Decision: {summary}" if summary else "Agent Decision Recorded",
            summary=rationale or summary,
            correlation_id=str(event.correlation_id) if event.correlation_id else None,
            causation_id=str(event.causation_id) if event.causation_id else None,
            actor_type=actor_type,
            primary_entity=primary_entity,
            entities=list(entities),
            metadata=metadata,
        )

    def _project_approval_requested(self, event: AgentApprovalRequestedEvent) -> TimelineItem:
        approval_id = event.approval_id
        payload = event.approval_payload or {}
        title = payload.get("title") or "Approval Requested"
        asset = payload.get("asset")
        base_commit = payload.get("base_commit")
        entities = []
        if asset:
            entities.append(EntityRef(type="ASSET", id=asset))
        if base_commit:
            entities.append(EntityRef(type="COMMIT", id=base_commit))
        if approval_id:
            entities.append(EntityRef(type="APPROVAL", id=approval_id))
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.APPROVAL,
            severity="WARNING",
            title=f"Approval Requested: {title}",
            summary=payload.get("description") or title,
            correlation_id=str(event.correlation_id) if event.correlation_id else None,
            causation_id=str(event.causation_id) if event.causation_id else None,
            actor_type="AGENT",
            primary_entity=EntityRef(type="APPROVAL", id=approval_id) if approval_id else None,
            entities=entities,
            metadata=payload,
        )

    def _project_approval_resolved(self, event: AgentApprovalResolvedEvent) -> TimelineItem:
        approval_id = event.approval_id
        decision = event.decision
        payload = event.approval_payload or {}
        entities = [EntityRef(type="APPROVAL", id=approval_id)] if approval_id else []
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.APPROVAL,
            severity="INFO",
            title=f"Proposal Decision: {decision.upper()}",
            summary=f"User {decision} proposal {approval_id}",
            correlation_id=str(event.correlation_id) if event.correlation_id else None,
            causation_id=str(event.causation_id) if event.causation_id else None,
            actor_type="USER",
            primary_entity=EntityRef(type="APPROVAL", id=approval_id) if approval_id else None,
            entities=entities,
            metadata={"decision": decision, "approval_id": approval_id, "payload": payload},
        )

    def _project_action_created(self, event: AgentActionCreatedEvent) -> TimelineItem:
        action_id = event.action_id
        payload = event.action_payload or {}
        title = payload.get("title") or "Action Created"
        action_type = payload.get("type") or "ACTION"
        entities = [EntityRef(type="ACTION", id=action_id)] if action_id else []
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.AGENT,
            severity="INFO",
            title=f"Agent Action: {title}",
            summary=f"Created {action_type} action: {title}",
            correlation_id=str(event.correlation_id) if event.correlation_id else None,
            causation_id=str(event.causation_id) if event.causation_id else None,
            actor_type="AGENT",
            primary_entity=EntityRef(type="ACTION", id=action_id) if action_id else None,
            entities=entities,
            metadata=payload,
        )

    def _project_action_completed(self, event: AgentActionCompletedEvent) -> TimelineItem:
        action_id = event.action_id
        payload = event.result_payload or {}
        entities = [EntityRef(type="ACTION", id=action_id)] if action_id else []
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.AGENT,
            severity="INFO",
            title=f"Action Completed: {action_id[:8] if action_id else ''}",
            summary=f"Agent action {action_id} completed successfully",
            correlation_id=str(event.correlation_id) if event.correlation_id else None,
            causation_id=str(event.causation_id) if event.causation_id else None,
            actor_type="AGENT",
            primary_entity=EntityRef(type="ACTION", id=action_id) if action_id else None,
            entities=entities,
            metadata=payload,
        )

    def _project_action_failed(self, event: AgentActionFailedEvent) -> TimelineItem:
        action_id = event.action_id
        error = event.error or "Action execution failed"
        entities = [EntityRef(type="ACTION", id=action_id)] if action_id else []
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.AGENT,
            severity="ERROR",
            title=f"Action Failed: {action_id[:8] if action_id else ''}",
            summary=f"Agent action {action_id} failed: {error}",
            correlation_id=str(event.correlation_id) if event.correlation_id else None,
            causation_id=str(event.causation_id) if event.causation_id else None,
            actor_type="AGENT",
            primary_entity=EntityRef(type="ACTION", id=action_id) if action_id else None,
            entities=entities,
            metadata={"action_id": action_id, "error": error},
        )

    def _project_oracle_summary(self, event: OracleSummaryEvent) -> TimelineItem:
        summary_text = event.summary
        symbol = event.symbol
        entities = [EntityRef(type="ASSET", id=symbol)] if symbol else []
        metadata = event.payload.to_dict()
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.AGENT,
            severity="INFO",
            title=f"Oracle Summary: {symbol}" if symbol else "Oracle Summary",
            summary=summary_text[:120] if summary_text else "Trading state summarized by LLM Oracle",
            correlation_id=event.correlation_id,
            causation_id=None,
            actor_type="AGENT",
            primary_entity=EntityRef(type="ASSET", id=symbol) if symbol else None,
            entities=entities,
            metadata=metadata,
        )

    def _project_vcs(self, event: RefChangedEvent) -> TimelineItem:
        ref = event.ref
        commit_hash = event.commit_hash
        entities = [EntityRef(type="COMMIT", id=commit_hash)] if commit_hash else []
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.VCS,
            severity="INFO",
            title=f"VCS Updated: {ref}",
            summary=f"Ref {ref} pointed to commit {commit_hash[:8] if commit_hash else ''}",
            correlation_id=None,
            causation_id=None,
            actor_type="SYSTEM",
            primary_entity=EntityRef(type="COMMIT", id=commit_hash) if commit_hash else None,
            entities=entities,
            metadata={"ref": ref, "commit_hash": commit_hash},
        )

    def _project_runtime_error(self, event: RuntimeErrorCapturedEvent) -> TimelineItem:
        error_type = event.error_type
        message = event.message
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.RUNTIME,
            severity="ERROR",
            title=f"Runtime Error: {error_type}",
            summary=message or error_type,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            actor_type=event.actor_type,
            primary_entity=None,
            entities=[],
            metadata={"error_type": error_type, "message": message},
        )

    def _project_runtime_incident(self, event: RuntimeIncidentCreatedEvent) -> TimelineItem:
        incident_id = event.incident_id
        summary = event.summary or f"Runtime incident {incident_id}"
        severity = event.severity
        entities = [EntityRef(type="INCIDENT", id=incident_id)] if incident_id else []
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.RUNTIME,
            severity=severity.upper() if severity else "ERROR",
            title=f"Runtime Incident: {incident_id[:8] if incident_id else ''}",
            summary=summary,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            actor_type=event.actor_type,
            primary_entity=EntityRef(type="INCIDENT", id=incident_id) if incident_id else None,
            entities=entities,
            metadata={"incident_id": incident_id, "summary": summary},
        )

    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    def list_items(
            self,
            category: Optional[str] = None,
            severity: Optional[str] = None,
            entity_type: Optional[str] = None,
            entity_id: Optional[str] = None,
            since: Optional[datetime] = None,
            until: Optional[datetime] = None,
            days: Optional[int] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[dict]:
        if days is not None and days > 0 and since is None:
            since = datetime.now(timezone.utc) - timedelta(days=days)

        if self._db_manager:
            self.flush()
            try:
                with self._db_manager.get_unit_of_work() as uow:
                    repo = uow.get_repository(PostgresTimelineRepository)
                    db_items = repo.list_items(
                        category=category,
                        severity=severity,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        since=since,
                        until=until,
                        limit=limit,
                        offset=offset,
                    )
                    if db_items:
                        return [i.to_dict() for i in db_items]
            except Exception as err:
                self.app_logger.debug(f"Querying DB for timeline items failed, falling back to memory: {err}")

        with self._lock:
            items = list(self._items)

        if category:
            cat_upper = category.upper()
            items = [i for i in items if cat_upper in (i.category.value, i.category)]

        if severity:
            sev_upper = severity.upper()
            items = [i for i in items if i.severity.upper() == sev_upper]

        if entity_type:
            et_upper = entity_type.upper()
            items = [i for i in items if any(e.type.upper() == et_upper for e in i.entities)]

        if entity_id:
            items = [i for i in items if any(e.id == entity_id for e in i.entities)]

        if since is not None:
            items = [i for i in items if FormatHelper.parse_iso_datetime(i.timestamp) >= since]

        if until is not None:
            items = [i for i in items if FormatHelper.parse_iso_datetime(i.timestamp) <= until]

        items.reverse()  # Newest first
        return [i.to_dict() for i in items[offset:offset + limit]]
