from __future__ import annotations

from typing import Any

from src.agent.runtime_debug.state import RuntimeDebugPresentation, RuntimeDebugState


class PresentSuggestionNode:
    def __call__(self, state: RuntimeDebugState) -> dict[str, Any]:
        diagnosis = state.get("diagnosis")
        suggestion = state.get("suggestion")
        incident = state.get("incident")
        evidence = state.get("evidence") or []

        lines = ["### 🔴 Runtime Incident Diagnosis & Suggested Fix\n"]
        if incident:
            lines.append(f"**Asset:** `{incident.asset}` | **Exchange:** `{incident.exchange}` | **Occurrences:** `{incident.occurrence_count}`")
            lines.append(f"**Status:** `{incident.status.value}` | **Severity:** `{incident.severity.value}`\n")

        if diagnosis:
            lines.append(f"#### Diagnosis ({diagnosis.confidence.value})")
            lines.append(f"**Summary:** {diagnosis.summary}")
            lines.append(f"**Suspected Component:** `{diagnosis.suspected_component}`")
            lines.append(f"**Root Cause:** {diagnosis.suspected_root_cause}\n")

        if evidence:
            lines.append("#### Verified Evidence")
            for item in evidence:
                lines.append(f"- **{item.title}** ({item.source}): {item.description}")
            lines.append("")

        if suggestion:
            lines.append("#### Suggested Remediation (Human Approval Required)")
            lines.append(f"**Proposed Change:** {suggestion.proposed_change}")
            lines.append(f"**Rationale:** {suggestion.rationale}")
            lines.append(
                f"**Type:** {'Code Change' if suggestion.requires_code_change else 'Config Change'} | "
                f"**Risk Level:** `{suggestion.risk.value}`"
            )

        content = "\n".join(lines)
        presentation = RuntimeDebugPresentation(blocks=[{"type": "markdown", "content": content}])

        return {"presentation": presentation}
