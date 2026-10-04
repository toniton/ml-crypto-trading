from __future__ import annotations

from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.logging.application_logging_mixin import ApplicationLoggingMixin


class TradingHealthInput(BaseModel):
    scope_type: Optional[str] = Field(
        default=None,
        description="Filter by scope type: 'global', 'asset', 'quote_portfolio', 'exchange'. None for all.",
    )
    scope_identifier: Optional[str] = Field(
        default=None,
        description="Filter by specific scope identifier (e.g. 'BTC_USD', 'GLOBAL', 'USD', 'crypto_com').",
    )


class TradingHealthTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "trading_health"
    description: str = (
        "Inspects the live operational trading health state machine: current engine state "
        "(TRADING, RECOVERING, DEGRADED, PAUSED, SYNCING, STARTING, STOPPING, STOPPED), "
        "active health conditions and incidents (with observed values and limit thresholds), "
        "effective trading permissions (new_orders, modify_orders, cancel_orders, reduce_positions, close_positions), "
        "and recovery hysteresis status."
    )
    args_schema: Type[BaseModel] = TradingHealthInput
    health_monitor: Any

    def __init__(self, health_monitor: Any):
        super().__init__(health_monitor=health_monitor)

    def _run(
        self,
        *args: Any,
        scope_type: Optional[str] = None,
        scope_identifier: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        snapshot = self.health_monitor.snapshot
        perms_str = ", ".join(sorted(p.value for p in snapshot.effective_permissions)) or "NONE"
        lines: list[str] = [
            f"Trading Health State: {snapshot.state.value}",
            f"Snapshot Version: v{snapshot.version}",
            f"Last Updated: {snapshot.updated_at.isoformat()}",
            f"Global Effective Permissions: {perms_str}",
        ]

        # Provide context on the state meaning
        if snapshot.state.value == "RECOVERING":
            lines.append(
                "State Context: Engine is in RECOVERING. It is completing recovery consistency checks or awaiting "
                "consecutive healthy observation cycles (anti-flapping hysteresis) before promoting to TRADING."
            )
        elif snapshot.state.value == "PAUSED":
            lines.append(
                "State Context: Engine is PAUSED due to critical safety conditions or manual operator pause. "
                "New orders are blocked."
            )
        elif snapshot.state.value == "DEGRADED":
            lines.append(
                "State Context: Engine is DEGRADED due to non-critical issues. Isolated healthy scopes can continue, "
                "while affected scopes are restricted."
            )

        active = list(snapshot.active_conditions)
        if scope_type:
            target_st = scope_type.strip().lower()
            active = [c for c in active if c.scope.scope_type.value.lower() == target_st]
        if scope_identifier:
            target_id = scope_identifier.strip().upper()
            active = [c for c in active if c.scope.identifier.upper() == target_id]

        if not active:
            lines.append("Active Health Conditions: None (all monitored subsystems healthy).")
        else:
            lines.append(f"Active Health Conditions ({len(active)}):")
            for idx, c in enumerate(active, 1):
                val_str = f", Measured: {c.measured_value}" if c.measured_value is not None else ""
                thr_str = f", Limit: {c.threshold}" if c.threshold is not None else ""
                lines.append(
                    f"  {idx}. [{c.severity.value.upper()}] {c.condition.value} "
                    f"on {c.scope.scope_type.value.upper()}:{c.scope.identifier} "
                    f"(Consecutive healthy checks: {c.consecutive_healthy_checks}{val_str}{thr_str}, "
                    f"first detected: {c.first_detected_at.isoformat()})"
                )

        return "\n".join(lines)
