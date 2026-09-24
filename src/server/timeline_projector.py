from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from src.agent.oracle.events import OracleSummaryEvent
from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
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
from src.trading.events import (
    ConsensusEvaluatedEvent,
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
    PositionChangedEvent,
    RiskStateChangedEvent,
)
from src.vcs.application.events import RefChangedEvent

TIMELINE_EVENT_CLASSES = (
    OrderSubmittedEvent,
    OrderFilledEvent,
    OrderCancelledEvent,
    OrderRejectedEvent,
    PositionChangedEvent,
    RiskStateChangedEvent,
    ConsensusEvaluatedEvent,
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
)

TIMELINE_EVENT_TYPES = tuple(cls.__name__ for cls in TIMELINE_EVENT_CLASSES)


class TimelineProjector(ApplicationLoggingMixin):
    """Projects significant domain events into indexable TimelineItem read models."""

    def __init__(self, event_bus: EventBus, max_items: int = 1000):
        self._event_bus = event_bus
        self._max_items = max_items
        self._items: list[TimelineItem] = []
        self._lock = threading.Lock()
        self._subscriptions: list[str] = []

    def subscribe(self) -> None:
        for event_type in TIMELINE_EVENT_TYPES:
            self._subscriptions.append(
                self._event_bus.subscribe(event_type, CallbackSubscription(self._on_event))
            )

    def close(self) -> None:
        for sub_id in self._subscriptions:
            self._event_bus.unsubscribe(sub_id)
        self._subscriptions.clear()

    def _on_event(self, event: Event) -> None:
        item = self._project_event(event)
        if item is not None:
            self._append_item(item)

    def _append_item(self, item: TimelineItem) -> None:
        with self._lock:
            self._items.append(item)
            if len(self._items) > self._max_items:
                self._items.pop(0)

    def _project_event(self, event: Event) -> Optional[TimelineItem]:  # pylint: disable=too-many-return-statements
        class_name = type(event).__name__
        event_type = getattr(event, "type", None) or class_name
        event_names = {event_type, class_name}
        if hasattr(event, "EVENT_TYPE"):
            event_names.add(getattr(event, "EVENT_TYPE"))

        timestamp = getattr(event, "timestamp", None) or datetime.now(timezone.utc).isoformat()
        correlation_id = getattr(event, "correlation_id", None)
        causation_id = getattr(event, "causation_id", None)
        actor_type = getattr(event, "actor_type", "SYSTEM")

        if event_names & {OrderSubmittedEvent.__name__}:
            return self._project_order_submitted(event, timestamp, correlation_id, causation_id, actor_type)

        if event_names & {OrderFilledEvent.__name__}:
            return self._project_order_filled(event, timestamp, correlation_id, causation_id)

        if event_names & {OrderRejectedEvent.__name__}:
            return self._project_order_rejected(event, timestamp, correlation_id, causation_id)

        if event_names & {ConsensusEvaluatedEvent.__name__, "consensus_evaluated"}:
            return self._project_consensus(event, timestamp, correlation_id, causation_id)

        if event_names & {TradingActivityAnomalyDetectedEvent.__name__, TradingActivityAnomalyDetectedEvent.EVENT_TYPE}:
            return self._project_anomaly(event, timestamp, correlation_id, causation_id)

        if event_names & {AgentApprovalRequestedEvent.__name__, AgentApprovalRequestedEvent.EVENT_TYPE}:
            return self._project_approval_requested(event, timestamp, correlation_id, causation_id)

        if event_names & {AgentApprovalResolvedEvent.__name__, AgentApprovalResolvedEvent.EVENT_TYPE}:
            return self._project_approval_resolved(event, timestamp, correlation_id, causation_id)

        if event_names & {AgentActionCreatedEvent.__name__, AgentActionCreatedEvent.EVENT_TYPE}:
            return self._project_action_created(event, timestamp, correlation_id, causation_id)

        if event_names & {RefChangedEvent.__name__, "ref_changed"}:
            return self._project_vcs(event, timestamp, correlation_id, causation_id, actor_type)

        return None

    def _project_order_submitted(
            self, event: Event, timestamp: str, correlation_id: Optional[str],
            causation_id: Optional[str], actor_type: str,
    ) -> TimelineItem:
        order = getattr(event, "order", None)
        symbol = getattr(event, "symbol", "")
        order_id = getattr(order, "uuid", "") if order else ""
        action = getattr(order, "trade_action", "") if order else ""
        qty = str(getattr(order, "quantity", "")) if order else ""
        price = str(getattr(order, "price", "")) if order else ""
        entities = []
        if symbol:
            entities.append(EntityRef(type="ASSET", id=symbol))
        if order_id:
            entities.append(EntityRef(type="ORDER", id=order_id))
        return TimelineItem(
            timestamp=timestamp,
            category=TimelineCategory.TRADING,
            severity="INFO",
            title=f"Order Submitted: {symbol} {action}",
            summary=f"Submitted {action} order for {qty} {symbol} @ {price}",
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor_type=actor_type,
            primary_entity=EntityRef(type="ORDER", id=order_id) if order_id else None,
            entities=entities,
            metadata={"order_id": order_id, "symbol": symbol, "action": str(action)},
        )

    def _project_order_filled(
            self, event: Event, timestamp: str, correlation_id: Optional[str], causation_id: Optional[str],
    ) -> TimelineItem:
        order = getattr(event, "order", None)
        symbol = getattr(event, "symbol", "")
        order_id = getattr(order, "uuid", "") if order else ""
        fill_price = str(getattr(order, "fill_price", None) or getattr(order, "price", "")) if order else ""
        entities = []
        if symbol:
            entities.append(EntityRef(type="ASSET", id=symbol))
        if order_id:
            entities.append(EntityRef(type="ORDER", id=order_id))
        return TimelineItem(
            timestamp=timestamp,
            category=TimelineCategory.TRADING,
            severity="INFO",
            title=f"Order Filled: {symbol}",
            summary=f"Order {order_id} filled @ {fill_price}",
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor_type="EXCHANGE",
            primary_entity=EntityRef(type="ORDER", id=order_id) if order_id else None,
            entities=entities,
            metadata={"order_id": order_id, "symbol": symbol, "fill_price": fill_price},
        )

    def _project_order_rejected(
            self, event: Event, timestamp: str, correlation_id: Optional[str], causation_id: Optional[str],
    ) -> TimelineItem:
        order = getattr(event, "order", None)
        symbol = getattr(event, "symbol", "")
        reason = getattr(event, "reason", "")
        order_id = getattr(order, "uuid", "") if order else ""
        entities = []
        if symbol:
            entities.append(EntityRef(type="ASSET", id=symbol))
        if order_id:
            entities.append(EntityRef(type="ORDER", id=order_id))
        return TimelineItem(
            timestamp=timestamp,
            category=TimelineCategory.TRADING,
            severity="WARNING",
            title=f"Order Rejected: {symbol}",
            summary=f"Order rejected: {reason}",
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor_type="EXCHANGE",
            primary_entity=EntityRef(type="ORDER", id=order_id) if order_id else None,
            entities=entities,
            metadata={"order_id": order_id, "reason": reason},
        )

    def _project_consensus(
            self, event: Event, timestamp: str, correlation_id: Optional[str], causation_id: Optional[str],
    ) -> TimelineItem:
        symbol = getattr(event, "symbol", "")
        decision = getattr(event, "decision", "")
        quorum_met = getattr(event, "quorum_met", False)
        buy_votes = getattr(event, "buy_votes", 0)
        sell_votes = getattr(event, "sell_votes", 0)
        entities = [EntityRef(type="ASSET", id=symbol)] if symbol else []
        return TimelineItem(
            timestamp=timestamp,
            category=TimelineCategory.DECISION,
            severity="INFO",
            title=f"Consensus Evaluated: {symbol} -> {decision}",
            summary=f"Consensus {decision} (Quorum: {quorum_met}, Buy: {buy_votes}, Sell: {sell_votes})",
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor_type="SYSTEM",
            primary_entity=EntityRef(type="ASSET", id=symbol) if symbol else None,
            entities=entities,
            metadata={
                "decision": decision,
                "quorum_met": quorum_met,
                "buy_votes": buy_votes,
                "sell_votes": sell_votes,
            },
        )

    def _project_anomaly(
            self, event: Event, timestamp: str, correlation_id: Optional[str], causation_id: Optional[str],
    ) -> TimelineItem:
        asset = getattr(event, "asset", "")
        anomaly_kind = getattr(event, "anomaly_kind", "")
        threshold = getattr(event, "threshold", 0.0)
        entities = [EntityRef(type="ASSET", id=asset)] if asset else []
        return TimelineItem(
            timestamp=timestamp,
            category=TimelineCategory.AGENT,
            severity="WARNING",
            title=f"Trading Starvation Detected: {asset}",
            summary=f"Watchdog detected {anomaly_kind} beyond {threshold:.0f}s threshold",
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor_type="WATCHDOG",
            primary_entity=EntityRef(type="ASSET", id=asset) if asset else None,
            entities=entities,
            metadata={"asset": asset, "anomaly_kind": anomaly_kind, "threshold": threshold},
        )

    def _project_approval_requested(
            self, event: Event, timestamp: str, correlation_id: Optional[str], causation_id: Optional[str],
    ) -> TimelineItem:
        approval_id = getattr(event, "approval_id", "")
        payload = getattr(event, "approval_payload", None) or {}
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
            timestamp=timestamp,
            category=TimelineCategory.APPROVAL,
            severity="WARNING",
            title=f"Approval Requested: {title}",
            summary=payload.get("description") or title,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor_type="AGENT",
            primary_entity=EntityRef(type="APPROVAL", id=approval_id) if approval_id else None,
            entities=entities,
            metadata=payload,
        )

    def _project_approval_resolved(
            self, event: Event, timestamp: str, correlation_id: Optional[str], causation_id: Optional[str],
    ) -> TimelineItem:
        approval_id = getattr(event, "approval_id", "")
        decision = getattr(event, "decision", "")
        payload = getattr(event, "approval_payload", None) or {}
        entities = [EntityRef(type="APPROVAL", id=approval_id)] if approval_id else []
        return TimelineItem(
            timestamp=timestamp,
            category=TimelineCategory.APPROVAL,
            severity="INFO",
            title=f"Proposal Decision: {decision.upper()}",
            summary=f"User {decision} proposal {approval_id}",
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor_type="USER",
            primary_entity=EntityRef(type="APPROVAL", id=approval_id) if approval_id else None,
            entities=entities,
            metadata={"decision": decision, "approval_id": approval_id, "payload": payload},
        )

    def _project_action_created(
            self, event: Event, timestamp: str, correlation_id: Optional[str], causation_id: Optional[str],
    ) -> TimelineItem:
        action_id = getattr(event, "action_id", "")
        payload = getattr(event, "action_payload", None) or {}
        title = payload.get("title") or "Action Created"
        action_type = payload.get("type") or "ACTION"
        entities = [EntityRef(type="ACTION", id=action_id)] if action_id else []
        return TimelineItem(
            timestamp=timestamp,
            category=TimelineCategory.AGENT,
            severity="INFO",
            title=f"Agent Action: {title}",
            summary=f"Created {action_type} action: {title}",
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor_type="AGENT",
            primary_entity=EntityRef(type="ACTION", id=action_id) if action_id else None,
            entities=entities,
            metadata=payload,
        )

    def _project_vcs(
            self, event: Event, timestamp: str, correlation_id: Optional[str],
            causation_id: Optional[str], actor_type: str,
    ) -> TimelineItem:
        ref = getattr(event, "ref", "")
        commit_hash = getattr(event, "commit_hash", "")
        entities = [EntityRef(type="COMMIT", id=commit_hash)] if commit_hash else []
        return TimelineItem(
            timestamp=timestamp,
            category=TimelineCategory.VCS,
            severity="INFO",
            title=f"VCS Updated: {ref}",
            summary=f"Ref {ref} pointed to commit {commit_hash[:8] if commit_hash else ''}",
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor_type=actor_type,
            primary_entity=EntityRef(type="COMMIT", id=commit_hash) if commit_hash else None,
            entities=entities,
            metadata={"ref": ref, "commit_hash": commit_hash},
        )

    def list_items(
            self,
            category: Optional[str] = None,
            severity: Optional[str] = None,
            entity_type: Optional[str] = None,
            entity_id: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[dict]:
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

        items.reverse()  # Newest first
        return [i.to_dict() for i in items[offset:offset + limit]]
