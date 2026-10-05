from __future__ import annotations

import threading
from typing import Optional

from src.trading.health.enums import TradingHealthCondition
from src.trading.health.models import ActiveCondition, HealthObservation, HealthScope
from src.trading.health.recovery_policy import RecoveryPolicy


class ConditionRegistry:
    def __init__(self, recovery_policy: RecoveryPolicy) -> None:
        self._recovery_policy = recovery_policy
        self._lock = threading.Lock()
        self._active_conditions: dict[tuple[TradingHealthCondition, str, str], ActiveCondition] = {}

    @staticmethod
    def _make_key(
            condition: TradingHealthCondition, scope: HealthScope
    ) -> tuple[TradingHealthCondition, str, str]:
        return condition, scope.scope_type.value, scope.identifier

    def record_observation(
            self, observation: HealthObservation
    ) -> tuple[bool, Optional[ActiveCondition], Optional[ActiveCondition]]:
        """
        Records an observation.
        Returns (changed, detected_condition, resolved_condition).
        """
        key = self._make_key(observation.condition, observation.scope)

        with self._lock:
            existing = (
                self._active_conditions[key]
                if key in self._active_conditions
                else None
            )

            if not observation.healthy:
                if existing is None:
                    new_condition = ActiveCondition(
                        condition=observation.condition,
                        scope=observation.scope,
                        severity=observation.severity,
                        first_detected_at=observation.observed_at,
                        last_observed_at=observation.observed_at,
                        measured_value=observation.measured_value,
                        threshold=observation.threshold,
                        consecutive_healthy_checks=0,
                        metadata=dict(observation.metadata),
                    )
                    self._active_conditions[key] = new_condition
                    return True, new_condition, None

                updated = ActiveCondition(
                    condition=existing.condition,
                    scope=existing.scope,
                    severity=observation.severity,
                    first_detected_at=existing.first_detected_at,
                    last_observed_at=observation.observed_at,
                    measured_value=observation.measured_value,
                    threshold=observation.threshold,
                    consecutive_healthy_checks=0,
                    metadata=dict(observation.metadata),
                )
                self._active_conditions[key] = updated
                return False, None, None

            if existing is not None:
                new_checks = existing.consecutive_healthy_checks + 1
                updated = ActiveCondition(
                    condition=existing.condition,
                    scope=existing.scope,
                    severity=existing.severity,
                    first_detected_at=existing.first_detected_at,
                    last_observed_at=observation.observed_at,
                    measured_value=observation.measured_value,
                    threshold=observation.threshold,
                    consecutive_healthy_checks=new_checks,
                    metadata=dict(existing.metadata),
                )

                if self._recovery_policy.can_resolve(updated, observation.observed_at):
                    del self._active_conditions[key]
                    return True, None, updated

                self._active_conditions[key] = updated
                return False, None, None

            return False, None, None

    def resolve_manually(
            self, condition: TradingHealthCondition, scope: HealthScope
    ) -> Optional[ActiveCondition]:
        key = self._make_key(condition, scope)
        with self._lock:
            if key in self._active_conditions:
                return self._active_conditions.pop(key)
            return None

    def get_active_conditions(self) -> tuple[ActiveCondition, ...]:
        with self._lock:
            return tuple(condition for condition in self._active_conditions.values())

    def clear(self) -> None:
        with self._lock:
            self._active_conditions.clear()
