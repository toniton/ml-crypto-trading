from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.trading.health.enums import ConditionSeverity
from src.trading.health.models import ActiveCondition


@dataclass(frozen=True)
class RecoveryConfig:
    automatic: bool = True
    stable_period_seconds: float = 10.0
    required_successful_checks: int = 3


class RecoveryPolicy:
    def __init__(self, config: RecoveryConfig) -> None:
        self._config = config

    @classmethod
    def default(cls) -> RecoveryPolicy:
        return cls(RecoveryConfig())

    @property
    def config(self) -> RecoveryConfig:
        return self._config

    def can_resolve(self, condition: ActiveCondition, current_time: datetime) -> bool:
        if condition.severity == ConditionSeverity.FATAL:
            return False

        if not self._config.automatic:
            return False

        if condition.consecutive_healthy_checks < self._config.required_successful_checks:
            return False

        elapsed_seconds = (current_time - condition.last_observed_at).total_seconds()
        return elapsed_seconds >= 0.0
