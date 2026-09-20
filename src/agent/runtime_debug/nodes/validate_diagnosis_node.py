from __future__ import annotations

from typing import Any

from src.agent.runtime_debug.state import RuntimeDebugState


class ValidateDiagnosisNode:
    def __call__(self, state: RuntimeDebugState) -> dict[str, Any]:
        diagnosis = state.get("diagnosis")
        evidence = state.get("evidence") or []

        is_valid = bool(diagnosis and diagnosis.summary and len(evidence) > 0)
        return {
            "validation_passed": is_valid,
        }
