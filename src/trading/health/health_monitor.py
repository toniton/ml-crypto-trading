from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Optional

from src.core.interfaces.event_bus import EventBus
from src.trading.events.domain_events import (
    TradingHealthConditionDetectedEvent,
    TradingHealthConditionResolvedEvent,
    TradingHealthStateChangedEvent,
    TradingPermissionsChangedEvent,
)
from src.trading.health.condition_registry import ConditionRegistry
from src.trading.health.enums import (
    TradingHealthCondition,
    TradingHealthState,
    TradingPermission,
)
from src.trading.health.models import (
    HealthObservation,
    HealthScope,
    TradingHealthSnapshot,
)
from src.trading.health.recovery_policy import RecoveryConfig, RecoveryPolicy
from src.trading.health.state_machine import TradingHealthStateMachine

logger = logging.getLogger(__name__)


class HealthMonitor:
    def __init__(
            self,
            event_bus: Optional[EventBus] = None,
            recovery_config: Optional[RecoveryConfig] = None,
            initial_state: TradingHealthState = TradingHealthState.STARTING,
    ) -> None:
        self._event_bus = event_bus
        self._recovery_policy = RecoveryPolicy(recovery_config)
        self._condition_registry = ConditionRegistry(self._recovery_policy)
        self._state_machine = TradingHealthStateMachine(initial_state)

    @property
    def current_state(self) -> TradingHealthState:
        return self._state_machine.current_state

    @property
    def snapshot(self) -> TradingHealthSnapshot:
        return self._state_machine.snapshot

    def get_snapshot(self) -> TradingHealthSnapshot:
        return self._state_machine.snapshot

    def report_observation(self, observation: HealthObservation) -> TradingHealthSnapshot:
        _changed, detected, resolved = self._condition_registry.record_observation(observation)
        prev_snapshot = self._state_machine.snapshot
        now_ts = observation.observed_at.timestamp()

        if detected is not None and self._event_bus is not None:
            self._event_bus.publish(
                TradingHealthConditionDetectedEvent(
                    condition=detected.condition.value,
                    scope_type=detected.scope.scope_type.value,
                    scope_identifier=detected.scope.identifier,
                    severity=detected.severity.value,
                    measured_value=detected.measured_value,
                    threshold=detected.threshold,
                    action_taken="RECORD_INCIDENT",
                    timestamp=now_ts,
                )
            )

        if resolved is not None and self._event_bus is not None:
            self._event_bus.publish(
                TradingHealthConditionResolvedEvent(
                    condition=resolved.condition.value,
                    scope_type=resolved.scope.scope_type.value,
                    scope_identifier=resolved.scope.identifier,
                    consecutive_healthy_checks=resolved.consecutive_healthy_checks,
                    timestamp=now_ts,
                )
            )

        active_conditions = self._condition_registry.get_active_conditions()
        has_state_or_condition_changed, new_snapshot = self._state_machine.update(active_conditions)

        if has_state_or_condition_changed:
            self._publish_snapshot_changes(prev_snapshot, new_snapshot, now_ts)

        return new_snapshot

    def set_state(
        self, target_state: TradingHealthState, current_time: Optional[datetime] = None
    ) -> TradingHealthSnapshot:
        now = current_time or datetime.now(timezone.utc)
        prev_snapshot = self._state_machine.snapshot
        active_conditions = self._condition_registry.get_active_conditions()
        has_changed, new_snapshot = self._state_machine.update(
            active_conditions, manual_override=target_state
        )

        if has_changed:
            self._publish_snapshot_changes(prev_snapshot, new_snapshot, now.timestamp())

        return new_snapshot

    def resolve_condition(
        self,
        condition: TradingHealthCondition,
        scope: HealthScope,
        current_time: Optional[datetime] = None,
    ) -> TradingHealthSnapshot:
        now = current_time or datetime.now(timezone.utc)
        resolved = self._condition_registry.resolve_manually(condition, scope)
        now_ts = now.timestamp()

        if resolved is not None and self._event_bus is not None:
            self._event_bus.publish(
                TradingHealthConditionResolvedEvent(
                    condition=resolved.condition.value,
                    scope_type=resolved.scope.scope_type.value,
                    scope_identifier=resolved.scope.identifier,
                    consecutive_healthy_checks=resolved.consecutive_healthy_checks,
                    timestamp=now_ts,
                )
            )

        prev_snapshot = self._state_machine.snapshot
        active_conditions = self._condition_registry.get_active_conditions()
        has_changed, new_snapshot = self._state_machine.update(active_conditions)

        if has_changed:
            self._publish_snapshot_changes(prev_snapshot, new_snapshot, now_ts)

        return new_snapshot

    def has_permission(
        self,
        scope: HealthScope,
        permission: TradingPermission,
        exchange_name: Optional[str] = None,
        quote_portfolio_key: Optional[str] = None,
    ) -> bool:
        effective_permissions = self._state_machine.evaluate_scope_permissions(
            scope,
            exchange_name=exchange_name,
            quote_portfolio_key=quote_portfolio_key,
        )
        return permission in effective_permissions

    def _publish_snapshot_changes(
        self,
        prev_snapshot: TradingHealthSnapshot,
        new_snapshot: TradingHealthSnapshot,
        timestamp: float,
    ) -> None:
        if self._event_bus is None:
            return

        if prev_snapshot.state != new_snapshot.state:
            logger.info(
                "Trading health state transitioned: %s -> %s (v%d)",
                prev_snapshot.state.value,
                new_snapshot.state.value,
                new_snapshot.version,
            )
            self._event_bus.publish(
                TradingHealthStateChangedEvent(
                    previous_state=prev_snapshot.state.value,
                    current_state=new_snapshot.state.value,
                    version=new_snapshot.version,
                    active_conditions_count=len(new_snapshot.active_conditions),
                    timestamp=timestamp,
                )
            )

        if prev_snapshot.effective_permissions != new_snapshot.effective_permissions:
            self._event_bus.publish(
                TradingPermissionsChangedEvent(
                    state=new_snapshot.state.value,
                    permissions=[p.value for p in new_snapshot.effective_permissions],
                    version=new_snapshot.version,
                    timestamp=timestamp,
                )
            )
