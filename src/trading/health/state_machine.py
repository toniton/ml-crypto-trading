from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Optional, Sequence

from src.trading.health.enums import (
    TradingHealthState,
    TradingPermission,
)
from src.trading.health.models import ActiveCondition, HealthScope, TradingHealthSnapshot
from src.trading.health.permission_policy import TradingPermissionPolicy
from src.trading.health.transition_policy import TradingTransitionPolicy


class TradingHealthStateMachine:
    def __init__(
            self,
            initial_state: TradingHealthState = TradingHealthState.STARTING,
    ) -> None:
        self._lock = threading.Lock()
        self._state = initial_state
        self._version = 1
        self._snapshot = self._build_snapshot(initial_state, (), 1)

    @property
    def current_state(self) -> TradingHealthState:
        with self._lock:
            return self._state

    @property
    def snapshot(self) -> TradingHealthSnapshot:
        with self._lock:
            return self._snapshot

    def update(
        self,
        active_conditions: Sequence[ActiveCondition],
        manual_override: Optional[TradingHealthState] = None,
    ) -> tuple[bool, TradingHealthSnapshot]:
        """
        Evaluates the transition and updates snapshot if state or conditions changed.
        Returns (has_changed, current_snapshot).
        """
        with self._lock:
            next_state = TradingTransitionPolicy.evaluate(
                self._state, active_conditions, manual_override=manual_override
            )

            state_changed = next_state != self._state
            conditions_changed = tuple(active_conditions) != self._snapshot.active_conditions

            if state_changed or conditions_changed:
                self._state = next_state
                self._version += 1
                self._snapshot = self._build_snapshot(
                    next_state, active_conditions, self._version
                )
                return True, self._snapshot

            return False, self._snapshot

    def _build_snapshot(
        self,
        state: TradingHealthState,
        active_conditions: Sequence[ActiveCondition],
        version: int,
    ) -> TradingHealthSnapshot:
        global_scope = HealthScope.global_scope()
        effective_permissions = TradingPermissionPolicy.evaluate(
            state, active_conditions, target_scope=global_scope
        )
        return TradingHealthSnapshot(
            state=state,
            active_conditions=tuple(active_conditions),
            effective_permissions=effective_permissions,
            version=version,
            updated_at=datetime.now(timezone.utc),
        )

    def evaluate_scope_permissions(
        self,
        scope: HealthScope,
        exchange_name: Optional[str] = None,
        quote_portfolio_key: Optional[str] = None,
    ) -> frozenset[TradingPermission]:
        with self._lock:
            return TradingPermissionPolicy.evaluate(
                self._state,
                self._snapshot.active_conditions,
                target_scope=scope,
                exchange_name=exchange_name,
                quote_portfolio_key=quote_portfolio_key,
            )
