from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.core.interfaces.event_bus import EventBus
from src.trading.health import (
    ActiveCondition,
    ConditionRegistry,
    ConditionSeverity,
    HealthMonitor,
    HealthObservation,
    HealthScope,
    RecoveryConfig,
    RecoveryPolicy,
    TradingHealthCondition,
    TradingHealthState,
    TradingPermission,
    TradingPermissionPolicy,
    TradingTransitionPolicy,
)


def test_health_scope_matching():
    global_scope = HealthScope.global_scope()
    exchange_scope = HealthScope.exchange_scope("crypto_com")
    portfolio_scope = HealthScope.quote_portfolio_scope("crypto_com:USD")
    asset_scope = HealthScope.asset_scope("BTC_USD")

    # Global encompasses everything
    assert global_scope.matches_target(asset_scope)
    assert global_scope.matches_target(exchange_scope)

    # Exchange matches target when exchange_name provided
    assert exchange_scope.matches_target(asset_scope, exchange_name="crypto_com")
    assert not exchange_scope.matches_target(asset_scope, exchange_name="binance")

    # Portfolio matches target when quote_portfolio_key provided
    assert portfolio_scope.matches_target(asset_scope, quote_portfolio_key="crypto_com:USD")
    assert not portfolio_scope.matches_target(asset_scope, quote_portfolio_key="crypto_com:EUR")

    # Asset only matches exact asset
    assert asset_scope.matches_target(HealthScope.asset_scope("BTC_USD"))
    assert not asset_scope.matches_target(HealthScope.asset_scope("ETH_USD"))


def test_transition_policy_deterministic_paths():
    now = datetime.now(timezone.utc)
    critical_condition = ActiveCondition(
        condition=TradingHealthCondition.EXCHANGE_UNAVAILABLE,
        scope=HealthScope.global_scope(),
        severity=ConditionSeverity.CRITICAL,
        first_detected_at=now,
        last_observed_at=now,
    )
    warning_condition = ActiveCondition(
        condition=TradingHealthCondition.MARKET_DATA_STALE,
        scope=HealthScope.asset_scope("BTC_USD"),
        severity=ConditionSeverity.WARNING,
        first_detected_at=now,
        last_observed_at=now,
    )

    # In TRADING, critical global transitions to PAUSED
    state = TradingTransitionPolicy.evaluate(
        TradingHealthState.TRADING, [critical_condition]
    )
    assert state == TradingHealthState.PAUSED

    # In TRADING, scoped/warning transitions to DEGRADED
    state = TradingTransitionPolicy.evaluate(
        TradingHealthState.TRADING, [warning_condition]
    )
    assert state == TradingHealthState.DEGRADED

    # In DEGRADED, clearing all conditions transitions to TRADING
    state = TradingTransitionPolicy.evaluate(TradingHealthState.DEGRADED, [])
    assert state == TradingHealthState.TRADING

    # In PAUSED, clearing conditions transitions to RECOVERING
    state = TradingTransitionPolicy.evaluate(TradingHealthState.PAUSED, [])
    assert state == TradingHealthState.RECOVERING

    # In RECOVERING, clearing conditions transitions to TRADING
    state = TradingTransitionPolicy.evaluate(TradingHealthState.RECOVERING, [])
    assert state == TradingHealthState.TRADING


def test_permission_policy_fail_closed():
    # STARTING, SYNCING, READY, STOPPED have 0 permissions
    assert len(TradingPermissionPolicy.evaluate(TradingHealthState.STARTING, [])) == 0
    assert len(TradingPermissionPolicy.evaluate(TradingHealthState.SYNCING, [])) == 0
    assert len(TradingPermissionPolicy.evaluate(TradingHealthState.READY, [])) == 0
    assert len(TradingPermissionPolicy.evaluate(TradingHealthState.STOPPED, [])) == 0


def test_permission_policy_scoped_isolation():
    now = datetime.now(timezone.utc)
    stale_btc = ActiveCondition(
        condition=TradingHealthCondition.MARKET_DATA_STALE,
        scope=HealthScope.asset_scope("BTC_USD"),
        severity=ConditionSeverity.CRITICAL,
        first_detected_at=now,
        last_observed_at=now,
    )

    btc_scope = HealthScope.asset_scope("BTC_USD")
    eth_scope = HealthScope.asset_scope("ETH_USD")

    # In DEGRADED state:
    btc_perms = TradingPermissionPolicy.evaluate(
        TradingHealthState.DEGRADED, [stale_btc], target_scope=btc_scope
    )
    eth_perms = TradingPermissionPolicy.evaluate(
        TradingHealthState.DEGRADED, [stale_btc], target_scope=eth_scope
    )

    # BTC loses NEW_ORDERS and CLOSE_POSITIONS due to stale price
    assert TradingPermission.NEW_ORDERS not in btc_perms
    assert TradingPermission.CANCEL_ORDERS in btc_perms
    assert TradingPermission.CLOSE_POSITIONS not in btc_perms

    # ETH remains healthy and retains all permissions!
    assert TradingPermission.NEW_ORDERS in eth_perms
    assert TradingPermission.CLOSE_POSITIONS in eth_perms


def test_condition_registry_hysteresis_recovery():
    recovery_config = RecoveryConfig(automatic=True, required_successful_checks=3)
    recovery_policy = RecoveryPolicy(config=recovery_config)
    registry = ConditionRegistry(recovery_policy=recovery_policy)
    # Using default config (3 checks)
    now = datetime.now(timezone.utc)
    scope = HealthScope.asset_scope("BTC_USD")

    obs_unhealthy = HealthObservation(
        source="market_feed",
        condition=TradingHealthCondition.MARKET_DATA_STALE,
        scope=scope,
        healthy=False,
        observed_at=now,
    )

    # 1. Report unhealthy
    changed, detected, resolved = registry.record_observation(obs_unhealthy)
    assert changed is True
    assert detected is not None
    assert len(registry.get_active_conditions()) == 1

    # 2. First healthy check -> not resolved yet
    obs_healthy = HealthObservation(
        source="market_feed",
        condition=TradingHealthCondition.MARKET_DATA_STALE,
        scope=scope,
        healthy=True,
        observed_at=now,
    )
    changed, detected, resolved = registry.record_observation(obs_healthy)
    assert changed is False
    assert resolved is None
    assert len(registry.get_active_conditions()) == 1

    # 3. Second healthy check -> not resolved yet
    changed, detected, resolved = registry.record_observation(obs_healthy)
    assert changed is False
    assert resolved is None

    # 4. Third healthy check -> hysteresis satisfied, resolved!
    changed, detected, resolved = registry.record_observation(obs_healthy)
    assert changed is True
    assert resolved is not None
    assert len(registry.get_active_conditions()) == 0


def test_health_monitor_coordination():
    monitor = HealthMonitor.create(
        event_bus=MagicMock(spec=EventBus),
        recovery_config=RecoveryConfig(),
        initial_state=TradingHealthState.STARTING,
    )
    assert monitor.current_state == TradingHealthState.STARTING

    # Transition lifecycle STARTING -> SYNCING -> READY -> TRADING
    monitor.set_state(TradingHealthState.SYNCING)
    assert monitor.current_state == TradingHealthState.SYNCING

    monitor.set_state(TradingHealthState.READY)
    assert monitor.current_state == TradingHealthState.READY

    monitor.set_state(TradingHealthState.TRADING)
    assert monitor.current_state == TradingHealthState.TRADING
    assert monitor.has_permission(HealthScope.global_scope(), TradingPermission.NEW_ORDERS)

    # Report critical global condition
    now = datetime.now(timezone.utc)
    snapshot = monitor.report_observation(
        HealthObservation(
            source="ws_client",
            condition=TradingHealthCondition.EXCHANGE_UNAVAILABLE,
            scope=HealthScope.global_scope(),
            healthy=False,
            observed_at=now,
        )
    )

    assert monitor.current_state == TradingHealthState.PAUSED
    assert not monitor.has_permission(HealthScope.global_scope(), TradingPermission.NEW_ORDERS)
    assert snapshot.version > 1
