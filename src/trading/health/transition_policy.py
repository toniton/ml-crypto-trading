from __future__ import annotations

from typing import Optional, Sequence

from src.trading.health.enums import (
    ConditionSeverity,
    ScopeType,
    TradingHealthState,
)
from src.trading.health.models import ActiveCondition


class TradingTransitionPolicy:
    @staticmethod
    def evaluate(
            current_state: TradingHealthState,
            active_conditions: Sequence[ActiveCondition],
            manual_override: Optional[TradingHealthState] = None,
    ) -> TradingHealthState:
        if manual_override is not None:
            return TradingTransitionPolicy._validate_manual_transition(
                current_state, manual_override, active_conditions
            )

        if current_state in (TradingHealthState.STARTING, TradingHealthState.STOPPING, TradingHealthState.STOPPED):
            return current_state

        has_critical_global = any(
            c.severity in (ConditionSeverity.CRITICAL, ConditionSeverity.FATAL)
            and c.scope.scope_type == ScopeType.GLOBAL
            for c in active_conditions
        )
        has_any_critical = any(
            c.severity in (ConditionSeverity.CRITICAL, ConditionSeverity.FATAL)
            for c in active_conditions
        )
        has_conditions = len(active_conditions) > 0

        if current_state == TradingHealthState.TRADING:
            if has_critical_global:
                return TradingHealthState.PAUSED
            if has_conditions:
                return TradingHealthState.DEGRADED
            return TradingHealthState.TRADING

        if current_state == TradingHealthState.DEGRADED:
            if has_critical_global:
                return TradingHealthState.PAUSED
            if not has_conditions:
                return TradingHealthState.TRADING
            return TradingHealthState.DEGRADED

        if current_state == TradingHealthState.PAUSED:
            if not has_critical_global and not has_any_critical:
                return TradingHealthState.RECOVERING
            return TradingHealthState.PAUSED

        if current_state == TradingHealthState.RECOVERING:
            if has_critical_global:
                return TradingHealthState.PAUSED
            if not has_conditions:
                return TradingHealthState.TRADING
            if not has_any_critical:
                return TradingHealthState.DEGRADED
            return TradingHealthState.RECOVERING

        if current_state == TradingHealthState.READY:
            if has_critical_global:
                return TradingHealthState.PAUSED
            if has_conditions:
                return TradingHealthState.DEGRADED
            return TradingHealthState.READY

        if current_state == TradingHealthState.SYNCING:
            if has_critical_global:
                return TradingHealthState.PAUSED
            return TradingHealthState.SYNCING

        return current_state

    @staticmethod
    def _validate_manual_transition(
            current_state: TradingHealthState,
            requested_state: TradingHealthState,
            active_conditions: Sequence[ActiveCondition],
    ) -> TradingHealthState:
        if requested_state == TradingHealthState.PAUSED:
            return TradingHealthState.PAUSED

        if requested_state == TradingHealthState.STOPPING:
            return TradingHealthState.STOPPING

        if requested_state == TradingHealthState.STOPPED:
            return TradingHealthState.STOPPED

        if requested_state == TradingHealthState.SYNCING:
            if current_state == TradingHealthState.STARTING:
                return TradingHealthState.SYNCING
            return current_state

        if requested_state == TradingHealthState.READY:
            if current_state in (TradingHealthState.STARTING, TradingHealthState.SYNCING):
                return TradingHealthState.READY
            return current_state

        if requested_state == TradingHealthState.TRADING:
            has_critical = any(
                c.severity in (ConditionSeverity.CRITICAL, ConditionSeverity.FATAL)
                for c in active_conditions
            )
            if has_critical:
                return TradingHealthState.PAUSED
            if len(active_conditions) > 0:
                return TradingHealthState.DEGRADED
            return TradingHealthState.TRADING

        if requested_state == TradingHealthState.RECOVERING:
            return TradingHealthState.RECOVERING

        return current_state
