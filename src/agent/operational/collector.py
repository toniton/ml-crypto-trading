from __future__ import annotations

from typing import Optional, Protocol

from src.agent.operational.models import (
    OperationalConditionSummary,
    OperationalContext,
    OperationalReadinessStatus,
)
from src.trading.health.enums import TradingHealthState, TradingPermission
from src.trading.health.health_monitor import HealthMonitor

_STATUS_MAPPING = {
    TradingHealthState.READY: OperationalReadinessStatus.READY,
    TradingHealthState.TRADING: OperationalReadinessStatus.READY,
    TradingHealthState.DEGRADED: OperationalReadinessStatus.DEGRADED,
    TradingHealthState.STARTING: OperationalReadinessStatus.DEGRADED,
    TradingHealthState.SYNCING: OperationalReadinessStatus.DEGRADED,
    TradingHealthState.RECOVERING: OperationalReadinessStatus.DEGRADED,
    TradingHealthState.PAUSED: OperationalReadinessStatus.PAUSED,
    TradingHealthState.STOPPING: OperationalReadinessStatus.HALTED,
    TradingHealthState.STOPPED: OperationalReadinessStatus.HALTED,
}


class OperationalContextCollectorProtocol(Protocol):
    def collect(self) -> OperationalContext:
        ...


class HealthMonitorContextCollector:
    def __init__(self, health_monitor: Optional[HealthMonitor] = None):
        self._health_monitor = health_monitor

    def collect(self) -> OperationalContext:
        if self._health_monitor is None:
            return OperationalContext.unavailable("No HealthMonitor configured")

        try:
            snapshot = self._health_monitor.get_snapshot()
            is_trading_allowed = TradingPermission.NEW_ORDERS in snapshot.effective_permissions
            status = _STATUS_MAPPING.get(snapshot.state, OperationalReadinessStatus.UNKNOWN)

            conditions = tuple(
                OperationalConditionSummary(
                    condition=condition.condition.value,
                    scope_type=condition.scope.scope_type.value,
                    scope_identifier=condition.scope.identifier,
                    severity=condition.severity.value,
                    first_detected_at=condition.first_detected_at,
                    last_observed_at=condition.last_observed_at,
                )
                for condition in snapshot.active_conditions
            )

            return OperationalContext(
                status=status,
                health_state=snapshot.state.value,
                is_trading_allowed=is_trading_allowed,
                active_conditions=conditions,
                effective_permissions=tuple(permission.value for permission in snapshot.effective_permissions),
                observed_at=snapshot.updated_at,
                snapshot_version=snapshot.version,
                is_available=True,
            )
        except Exception as exc:
            return OperationalContext.unavailable(f"Failed to collect health snapshot: {exc}")
