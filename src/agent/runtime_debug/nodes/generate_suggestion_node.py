from __future__ import annotations

from typing import Any, Optional

from src.agent.runtime_debug.models import DebugSuggestion, RiskLevel
from src.agent.runtime_debug.state import RuntimeDebugState
from src.core.interfaces.llm_adapter import LlmAdapter


class GenerateSuggestionNode:
    def __init__(self, llm: Optional[LlmAdapter] = None):
        self._llm = llm

    def __call__(self, state: RuntimeDebugState) -> dict[str, Any]:
        diagnosis = state.get("diagnosis")
        evidence = state.get("evidence") or []
        _error_event = state.get("error_event")

        has_precision_violation = any(
            e.data.get("violates_precision") or e.data.get("violates_min_quantity")
            for e in evidence
        )

        if has_precision_violation:
            suggestion = DebugSuggestion(
                summary="Normalize and quantize order quantity according to exchange instrument rules.",
                root_cause="Calculated order quantity does not conform to required decimal precision / step size.",
                affected_component="trading.orders.quantity_normalization",
                proposed_change=(
                    "Apply instrument decimal rounding to order quantity (e.g. quantize to instrument precision) "
                    "before submitting order to exchange."
                ),
                rationale="Exchange rejects non-conforming quantities deterministically with error 213.",
                evidence=evidence,
                risk=RiskLevel.HIGH,
                requires_code_change=True,
                requires_configuration_change=False,
                requires_restart=False,
                requires_manual_validation=True,
            )
        elif any(e.source == "exchange_http_response" and e.data.get("http_status") == 429 for e in evidence):
            suggestion = DebugSuggestion(
                summary="Enable exponential backoff and rate limit throttling on REST client.",
                root_cause="Request frequency exceeded exchange limits.",
                affected_component="exchange.clients.rest_client",
                proposed_change="Add retry-after delay handling and reduce polling frequency.",
                rationale="Prevents temporary account lockouts and dropped orders.",
                evidence=evidence,
                risk=RiskLevel.MEDIUM,
                requires_code_change=False,
                requires_configuration_change=True,
                requires_restart=False,
                requires_manual_validation=False,
            )
        else:
            summary = diagnosis.summary if diagnosis else "Investigate runtime failure"
            suggestion = DebugSuggestion(
                summary=summary,
                root_cause=diagnosis.suspected_root_cause if diagnosis else "Unknown",
                affected_component=diagnosis.suspected_component if diagnosis else "system",
                proposed_change="Review error stack trace and component state.",
                rationale="Manual review recommended for unclassified error.",
                evidence=evidence,
                risk=RiskLevel.HIGH,
                requires_code_change=True,
                requires_configuration_change=False,
                requires_restart=False,
                requires_manual_validation=True,
            )

        return {"suggestion": suggestion}
