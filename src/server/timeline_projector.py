from __future__ import annotations

import threading
from typing import Optional

from src.logging.factory import LoggingFactory

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


def _event_names_for(cls: type[Event]) -> set[str]:
    names = {cls.__name__}
    if cls.EVENT_TYPE:
        names.add(cls.EVENT_TYPE)
    else:
        LoggingFactory.get_application_logger(__name__).debug(
            "Event class '%s' has no EVENT_TYPE alias; projecting via class name.",
            cls.__name__,
        )
    return names


TIMELINE_EVENT_TYPES = tuple(
    name
    for cls in TIMELINE_EVENT_CLASSES
    for name in _event_names_for(cls)
)


class TimelineProjector(ApplicationLoggingMixin):
    """Projects significant domain events into indexable TimelineItem read models."""

    def __init__(self, event_bus: EventBus, max_items: int = 1000):
        self._event_bus = event_bus
        self._max_items = max_items
        self._items: list[TimelineItem] = []
        self._lock = threading.Lock()
        self._subscriptions: list[str] = []

    def subscribe(self) -> None:
        callback_sub = CallbackSubscription(self._on_event)
        for event_type in TIMELINE_EVENT_TYPES:
            self._subscriptions.append(
                self._event_bus.subscribe(event_type, callback_sub)
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

    # pylint: disable=too-many-return-statements,too-many-branches
    def _project_event(self, event: Event) -> Optional[TimelineItem]:
        if isinstance(event, OrderSubmittedEvent):
            return self._project_order_submitted(event)
        if isinstance(event, OrderFilledEvent):
            return self._project_order_filled(event)
        if isinstance(event, OrderCancelledEvent):
            return self._project_order_cancelled(event)
        if isinstance(event, OrderRejectedEvent):
            return self._project_order_rejected(event)
        if isinstance(event, PositionChangedEvent):
            return self._project_position_changed(event)
        if isinstance(event, RiskStateChangedEvent):
            return self._project_risk_state_changed(event)
        if isinstance(event, ConsensusEvaluatedEvent):
            return self._project_consensus(event)
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
        return None

    def _project_order_submitted(self, event: OrderSubmittedEvent) -> TimelineItem:
        order = event.order
        symbol = event.symbol
        order_id = order.uuid if order else ""
        action = order.trade_action if order else ""
        qty = str(order.quantity) if order else ""
        price = str(order.price) if order else ""
        entities = []
        if symbol:
            entities.append(EntityRef(type="ASSET", id=symbol))
        if order_id:
            entities.append(EntityRef(type="ORDER", id=order_id))
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.TRADING,
            severity="INFO",
            title=f"Order Submitted: {symbol} {action}",
            summary=f"Submitted {action} order for {qty} {symbol} @ {price}",
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            actor_type=event.actor_type,
            primary_entity=EntityRef(type="ORDER", id=order_id) if order_id else None,
            entities=entities,
            metadata={"order_id": order_id, "symbol": symbol, "action": str(action)},
        )

    def _project_order_filled(self, event: OrderFilledEvent) -> TimelineItem:
        order = event.order
        symbol = event.symbol
        order_id = order.uuid if order else ""
        fill_price = str(order.fill_price or order.price) if order else ""
        entities = []
        if symbol:
            entities.append(EntityRef(type="ASSET", id=symbol))
        if order_id:
            entities.append(EntityRef(type="ORDER", id=order_id))
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.TRADING,
            severity="INFO",
            title=f"Order Filled: {symbol}",
            summary=f"Order {order_id} filled @ {fill_price}",
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            actor_type="EXCHANGE",
            primary_entity=EntityRef(type="ORDER", id=order_id) if order_id else None,
            entities=entities,
            metadata={"order_id": order_id, "symbol": symbol, "fill_price": fill_price},
        )

    def _project_order_cancelled(self, event: OrderCancelledEvent) -> TimelineItem:
        order = event.order
        symbol = event.symbol
        order_id = order.uuid if order else ""
        entities = []
        if symbol:
            entities.append(EntityRef(type="ASSET", id=symbol))
        if order_id:
            entities.append(EntityRef(type="ORDER", id=order_id))
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.TRADING,
            severity="WARNING",
            title=f"Order Cancelled: {symbol}",
            summary=f"Order {order_id} was cancelled",
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            actor_type="EXCHANGE",
            primary_entity=EntityRef(type="ORDER", id=order_id) if order_id else None,
            entities=entities,
            metadata={"order_id": order_id, "symbol": symbol},
        )

    def _project_order_rejected(self, event: OrderRejectedEvent) -> TimelineItem:
        order = event.order
        symbol = event.symbol
        reason = event.reason
        order_id = order.uuid if order else ""
        entities = []
        if symbol:
            entities.append(EntityRef(type="ASSET", id=symbol))
        if order_id:
            entities.append(EntityRef(type="ORDER", id=order_id))
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.TRADING,
            severity="WARNING",
            title=f"Order Rejected: {symbol}",
            summary=f"Order rejected: {reason}",
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            actor_type="EXCHANGE",
            primary_entity=EntityRef(type="ORDER", id=order_id) if order_id else None,
            entities=entities,
            metadata={"order_id": order_id, "reason": reason},
        )

    def _project_position_changed(self, event: PositionChangedEvent) -> TimelineItem:
        symbol = event.symbol
        action = event.action
        qty = str(event.quantity)
        price = str(event.price)
        pos_qty = str(event.position_qty)
        pnl = str(event.realized_pnl)
        entities = [EntityRef(type="ASSET", id=symbol)] if symbol else []
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.TRADING,
            severity="INFO",
            title=f"Position Changed: {symbol} ({action})",
            summary=f"Position {action} {qty} @ {price} -> Total Qty: {pos_qty}, PnL: {pnl}",
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            actor_type=event.actor_type,
            primary_entity=EntityRef(type="ASSET", id=symbol) if symbol else None,
            entities=entities,
            metadata={
                "symbol": symbol,
                "action": action,
                "quantity": qty,
                "price": price,
                "position_qty": pos_qty,
                "realized_pnl": pnl,
            },
        )

    def _project_risk_state_changed(self, event: RiskStateChangedEvent) -> TimelineItem:
        symbol = event.symbol
        drawdown = str(event.drawdown)
        entities = [EntityRef(type="ASSET", id=symbol)] if symbol else []
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.TRADING,
            severity="WARNING",
            title=f"Risk State Changed: {symbol}",
            summary=f"Drawdown changed to {drawdown}",
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            actor_type=event.actor_type,
            primary_entity=EntityRef(type="ASSET", id=symbol) if symbol else None,
            entities=entities,
            metadata={"symbol": symbol, "drawdown": drawdown},
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
            metadata=decision.to_dict() if decision else {},
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
        summary = event.summary
        category = event.category
        return TimelineItem(
            timestamp=event.timestamp,
            category=TimelineCategory.AGENT,
            severity="INFO",
            title=f"Oracle Summary: {category}" if category else "Oracle Summary",
            summary=summary[:120] if summary else "Trading state summarized by LLM Oracle",
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            actor_type="AGENT",
            primary_entity=None,
            entities=[],
            metadata={"summary": summary, "category": category},
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
