from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.agent.operational.collector import HealthMonitorContextCollector
from src.agent.operational.models import (
    OperationalContext,
    OperationalReadinessStatus,
)
from src.core.severity import Severity
from src.trading.health.enums import (
    ScopeType,
    TradingHealthCondition,
    TradingHealthState,
    TradingPermission,
)
from src.trading.health.health_monitor import HealthMonitor
from src.trading.health.models import ActiveCondition, HealthScope, TradingHealthSnapshot


def _create_snapshot(
    state: TradingHealthState,
    conditions: tuple[ActiveCondition, ...] = (),
    permissions: frozenset[TradingPermission] = frozenset({TradingPermission.NEW_ORDERS}),
    version: int = 1,
    updated_at: datetime | None = None,
) -> TradingHealthSnapshot:
    return TradingHealthSnapshot(
        state=state,
        active_conditions=conditions,
        effective_permissions=permissions,
        version=version,
        updated_at=updated_at or datetime.now(timezone.utc),
    )


class TestHealthMonitorContextCollector:
    def test_unconfigured_monitor_returns_unavailable(self):
        collector = HealthMonitorContextCollector(None)
        context = collector.collect()
        assert context.is_available is False

    def test_unconfigured_monitor_has_unknown_status(self):
        collector = HealthMonitorContextCollector(None)
        context = collector.collect()
        assert context.status == OperationalReadinessStatus.UNKNOWN

    def test_trading_state_maps_to_ready_status(self):
        monitor = MagicMock(spec=HealthMonitor)
        monitor.get_snapshot.return_value = _create_snapshot(TradingHealthState.TRADING)
        collector = HealthMonitorContextCollector(monitor)
        context = collector.collect()
        assert context.status == OperationalReadinessStatus.READY

    def test_trading_permission_allows_trading(self):
        monitor = MagicMock(spec=HealthMonitor)
        monitor.get_snapshot.return_value = _create_snapshot(
            TradingHealthState.TRADING,
            permissions=frozenset({TradingPermission.NEW_ORDERS}),
        )
        collector = HealthMonitorContextCollector(monitor)
        context = collector.collect()
        assert context.is_trading_allowed is True

    def test_paused_state_maps_to_paused_status(self):
        monitor = MagicMock(spec=HealthMonitor)
        monitor.get_snapshot.return_value = _create_snapshot(
            TradingHealthState.PAUSED,
            permissions=frozenset({TradingPermission.CANCEL_ORDERS}),
        )
        collector = HealthMonitorContextCollector(monitor)
        context = collector.collect()
        assert context.status == OperationalReadinessStatus.PAUSED

    def test_stopped_state_maps_to_halted_status(self):
        monitor = MagicMock(spec=HealthMonitor)
        monitor.get_snapshot.return_value = _create_snapshot(
            TradingHealthState.STOPPED,
            permissions=frozenset(),
        )
        collector = HealthMonitorContextCollector(monitor)
        context = collector.collect()
        assert context.status == OperationalReadinessStatus.HALTED

    def test_degraded_state_with_active_conditions(self):
        now = datetime.now(timezone.utc)
        active_cond = ActiveCondition(
            condition=TradingHealthCondition.EXCHANGE_UNAVAILABLE,
            scope=HealthScope(scope_type=ScopeType.EXCHANGE, identifier="BINANCE"),
            severity=Severity.CRITICAL,
            first_detected_at=now,
            last_observed_at=now,
        )
        monitor = MagicMock(spec=HealthMonitor)
        monitor.get_snapshot.return_value = _create_snapshot(
            TradingHealthState.DEGRADED,
            conditions=(active_cond,),
            permissions=frozenset(),
        )
        collector = HealthMonitorContextCollector(monitor)
        context = collector.collect()
        assert len(context.active_conditions) == 1

    def test_exception_in_monitor_returns_unavailable_with_error(self):
        monitor = MagicMock(spec=HealthMonitor)
        monitor.get_snapshot.side_effect = RuntimeError("DB connection timeout")
        collector = HealthMonitorContextCollector(monitor)
        context = collector.collect()
        assert any("DB connection timeout" in error for error in context.collection_errors)

    def test_fresh_snapshot_is_not_stale(self):
        context = OperationalContext(
            status=OperationalReadinessStatus.READY,
            health_state="TRADING",
            is_trading_allowed=True,
            active_conditions=(),
            effective_permissions=("new_orders",),
            observed_at=datetime.now(timezone.utc),
            snapshot_version=1,
            is_available=True,
        )
        assert context.is_stale(max_age_seconds=60.0) is False

    def test_old_snapshot_is_stale(self):
        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        context = OperationalContext(
            status=OperationalReadinessStatus.READY,
            health_state="TRADING",
            is_trading_allowed=True,
            active_conditions=(),
            effective_permissions=("new_orders",),
            observed_at=old_time,
            snapshot_version=1,
            is_available=True,
        )
        assert context.is_stale(max_age_seconds=60.0) is True
