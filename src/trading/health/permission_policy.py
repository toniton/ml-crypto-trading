from __future__ import annotations

from typing import Optional, Sequence

from src.trading.health.enums import (
    TradingHealthCondition,
    TradingHealthState,
    TradingPermission,
)
from src.trading.health.models import ActiveCondition, HealthScope


class TradingPermissionPolicy:
    ALL_PERMISSIONS = frozenset({
        TradingPermission.NEW_ORDERS,
        TradingPermission.MODIFY_ORDERS,
        TradingPermission.CANCEL_ORDERS,
        TradingPermission.REDUCE_POSITIONS,
        TradingPermission.CLOSE_POSITIONS,
    })

    SAFE_SHUTDOWN_PERMISSIONS = frozenset({
        TradingPermission.CANCEL_ORDERS,
        TradingPermission.REDUCE_POSITIONS,
        TradingPermission.CLOSE_POSITIONS,
    })

    RECOVERY_PERMISSIONS = frozenset({
        TradingPermission.CANCEL_ORDERS,
        TradingPermission.REDUCE_POSITIONS,
    })

    @classmethod
    def evaluate(
            cls,
            state: TradingHealthState,
            active_conditions: Sequence[ActiveCondition],
            target_scope: Optional[HealthScope] = None,
            exchange_name: Optional[str] = None,
            quote_portfolio_key: Optional[str] = None,
    ) -> frozenset[TradingPermission]:
        if state in (
                TradingHealthState.STARTING,
                TradingHealthState.SYNCING,
                TradingHealthState.READY,
                TradingHealthState.STOPPED,
        ):
            return frozenset()

        is_exchange_down = any(
            c.condition == TradingHealthCondition.EXCHANGE_UNAVAILABLE
            and c.scope.matches_target(
                target_scope or HealthScope.global_scope(),
                exchange_name=exchange_name,
                quote_portfolio_key=quote_portfolio_key,
            )
            for c in active_conditions
        )

        if state == TradingHealthState.STOPPING:
            if is_exchange_down:
                return frozenset()
            return cls.SAFE_SHUTDOWN_PERMISSIONS

        if state == TradingHealthState.PAUSED:
            if is_exchange_down:
                return frozenset()
            return cls.RECOVERY_PERMISSIONS

        if state == TradingHealthState.RECOVERING:
            if is_exchange_down:
                return frozenset()
            return cls.RECOVERY_PERMISSIONS

        eval_scope = target_scope or HealthScope.global_scope()
        matching_conditions = [
            c for c in active_conditions
            if c.scope.matches_target(
                eval_scope,
                exchange_name=exchange_name,
                quote_portfolio_key=quote_portfolio_key,
            )
        ]

        if not matching_conditions:
            return cls.ALL_PERMISSIONS

        if is_exchange_down:
            return frozenset()

        permissions = set(cls.ALL_PERMISSIONS)

        for c in matching_conditions:
            if c.condition == TradingHealthCondition.MARKET_DATA_STALE:
                permissions.discard(TradingPermission.NEW_ORDERS)
                permissions.discard(TradingPermission.MODIFY_ORDERS)
                permissions.discard(TradingPermission.CLOSE_POSITIONS)
            elif c.condition in (
                    TradingHealthCondition.BALANCE_MISMATCH,
                    TradingHealthCondition.ORDER_RECONCILIATION_FAILED,
                    TradingHealthCondition.DATABASE_UNAVAILABLE,
                    TradingHealthCondition.CONFIG_INVALID,
            ):
                permissions.discard(TradingPermission.NEW_ORDERS)
                permissions.discard(TradingPermission.MODIFY_ORDERS)
            elif c.condition == TradingHealthCondition.RISK_LIMIT_BREACHED:
                permissions.discard(TradingPermission.NEW_ORDERS)
                permissions.discard(TradingPermission.MODIFY_ORDERS)

        return frozenset(permissions)
