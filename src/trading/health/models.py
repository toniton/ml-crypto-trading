from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from src.trading.health.enums import (
    ConditionSeverity,
    ScopeType,
    TradingHealthCondition,
    TradingHealthState,
    TradingPermission,
)


@dataclass(frozen=True)
class HealthScope:
    scope_type: ScopeType
    identifier: str = ""

    @classmethod
    def global_scope(cls) -> HealthScope:
        return cls(scope_type=ScopeType.GLOBAL, identifier="GLOBAL")

    @classmethod
    def exchange_scope(cls, exchange_name: str) -> HealthScope:
        return cls(scope_type=ScopeType.EXCHANGE, identifier=exchange_name)

    @classmethod
    def quote_portfolio_scope(cls, portfolio_key: str) -> HealthScope:
        return cls(scope_type=ScopeType.QUOTE_PORTFOLIO, identifier=portfolio_key)

    @classmethod
    def asset_scope(cls, ticker_symbol: str) -> HealthScope:
        return cls(scope_type=ScopeType.ASSET, identifier=ticker_symbol)

    def matches_target(
            self,
            target_scope: HealthScope,
            exchange_name: Optional[str] = None,
            quote_portfolio_key: Optional[str] = None,
    ) -> bool:
        """Determines if this condition scope encompasses the target evaluation scope."""
        if self.scope_type == ScopeType.GLOBAL:
            return True
        if self.scope_type == ScopeType.EXCHANGE:
            if target_scope.scope_type == ScopeType.EXCHANGE:
                return self.identifier == target_scope.identifier
            if exchange_name is not None:
                return self.identifier == exchange_name
            return False
        if self.scope_type == ScopeType.QUOTE_PORTFOLIO:
            if target_scope.scope_type == ScopeType.QUOTE_PORTFOLIO:
                return self.identifier == target_scope.identifier
            if quote_portfolio_key is not None:
                return self.identifier == quote_portfolio_key
            return False
        if self.scope_type == ScopeType.ASSET:
            return (
                    target_scope.scope_type == ScopeType.ASSET
                    and self.identifier == target_scope.identifier
            )
        return False


@dataclass(frozen=True)
class HealthObservation:
    source: str
    condition: TradingHealthCondition
    scope: HealthScope
    healthy: bool
    observed_at: datetime
    severity: ConditionSeverity = ConditionSeverity.CRITICAL
    measured_value: Optional[Any] = None
    threshold: Optional[Any] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActiveCondition:
    condition: TradingHealthCondition
    scope: HealthScope
    severity: ConditionSeverity
    first_detected_at: datetime
    last_observed_at: datetime
    measured_value: Optional[Any] = None
    threshold: Optional[Any] = None
    consecutive_healthy_checks: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TradingHealthSnapshot:
    state: TradingHealthState
    active_conditions: tuple[ActiveCondition, ...]
    effective_permissions: frozenset[TradingPermission]
    version: int
    updated_at: datetime
    details: dict[str, Any] = field(default_factory=dict)
