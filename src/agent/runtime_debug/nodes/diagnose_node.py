from __future__ import annotations

from typing import Any, Optional

from src.agent.runtime_debug.models import ConfidenceLevel, DebugDiagnosis
from src.agent.runtime_debug.state import RuntimeDebugState
from src.core.interfaces.llm_adapter import LlmAdapter


class DiagnoseNode:
    def __init__(self, llm: Optional[LlmAdapter] = None):
        self._llm = llm

    def __call__(self, state: RuntimeDebugState) -> dict[str, Any]:
        evidence = state.get("evidence") or []
        error_event = state.get("error_event")
        component = error_event.component if error_event else "runtime"

        # Check evidence for precision violations
        has_precision_violation = any(
            e.data.get("violates_precision") or e.data.get("violates_min_quantity")
            for e in evidence
        )

        if has_precision_violation:
            summary = (
                f"Exchange rejected order due to quantity precision / formatting mismatch on {error_event.exchange}."
            )
            root_cause = "Order quantity calculation produces non-normalized precision for instrument."
            confidence = ConfidenceLevel.CONFIRMED
        elif any(e.source == "exchange_http_response" and e.data.get("http_status") == 429 for e in evidence):
            summary = f"API rate limit exceeded on {error_event.exchange}."
            root_cause = "Request burst exceeded exchange rate limit threshold."
            confidence = ConfidenceLevel.CONFIRMED
        else:
            summary = f"Runtime error in {component}: {error_event.message if error_event else 'Unknown error'}."
            root_cause = "Runtime execution failure."
            confidence = ConfidenceLevel.LIKELY

        diagnosis = DebugDiagnosis(
            summary=summary,
            suspected_component=component,
            suspected_root_cause=root_cause,
            evidence=evidence,
            confidence=confidence,
        )

        return {"diagnosis": diagnosis, "confidence": confidence}
