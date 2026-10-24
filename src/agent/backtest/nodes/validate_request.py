from __future__ import annotations

from datetime import datetime

from src.agent.backtest.models import BacktestValidation
from src.agent.backtest.state import BacktestAgentState


class ValidateBacktestRequestNode:
    def __call__(self, state: BacktestAgentState) -> dict:
        agent_request = state["backtest_request"]
        resolved = state.get("resolved_request")
        errors: list[str] = []
        warnings: list[str] = []

        if agent_request.requires_clarification:
            errors.append(agent_request.clarification_question or "The request is ambiguous.")

        if resolved is None or not getattr(resolved, "ticker_symbol", None):
            errors.append("No asset was specified for the backtest.")

        self._validate_time_range(agent_request, resolved, errors, warnings)

        missing_execution = ValidateBacktestRequestNode._missing_execution_costs(agent_request)
        if missing_execution:
            errors.append(
                "Please provide the execution costs for the backtest: "
                + ", ".join(missing_execution)
                + "."
            )

        if errors:
            return {"validation": BacktestValidation.failed(errors, warnings)}
        return {"validation": BacktestValidation.ok(warnings)}

    @staticmethod
    def _validate_time_range(
            agent_request,
            resolved,
            errors: list[str],
            warnings: list[str],
    ) -> None:
        time_range = agent_request.time_range
        has_valid_time = (
            (time_range.mode == "relative" and time_range.duration_seconds and time_range.duration_seconds > 0)
            or (time_range.mode == "absolute" and time_range.start_time and time_range.end_time)
        )
        if not has_valid_time or (
            resolved is not None and (resolved.start_time is None or resolved.end_time is None)
        ):
            errors.append(
                "A valid time range (e.g. 'over the last 1 hour' or specific dates) "
                "must be specified for the backtest."
            )
        elif (
            resolved is not None
            and isinstance(resolved.start_time, datetime)
            and isinstance(resolved.end_time, datetime)
            and resolved.start_time >= resolved.end_time
        ):
            errors.append(
                "The backtest time range is invalid (start time must precede end time)."
            )
        elif (
            time_range.mode == "relative"
            and time_range.duration_seconds is not None
            and time_range.duration_seconds < 60
        ):
            warnings.append(
                "Very short window; the result may not be statistically meaningful."
            )

    @staticmethod
    def _missing_execution_costs(agent_request) -> list[str]:
        missing: list[str] = []
        if agent_request.fee_rate is None:
            missing.append("fee rate (e.g. 0.001)")
        if agent_request.slippage_ticks is None:
            missing.append("slippage in ticks (e.g. 2)")
        if agent_request.latency_ms is None:
            missing.append("latency in milliseconds (e.g. 500)")
        return missing
