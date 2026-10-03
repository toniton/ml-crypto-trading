from __future__ import annotations

from typing import Any

from src.agent.decision_investigation.models import DecisionInvestigationPresentation
from src.agent.decision_investigation.state import DecisionInvestigationState


class PresentExplanationNode:
    def __call__(self, state: DecisionInvestigationState) -> dict[str, Any]:
        evidence = state.get("evidence")
        explanation = state.get("explanation")

        lines: list[str] = ["### 🔍 Decision & Proposal Investigation\n"]

        asset = evidence.asset if evidence else None
        base_commit = evidence.base_commit if evidence else None
        resolved_commit = evidence.resolved_commit_hash if evidence else None
        status = evidence.approval_status if evidence else None

        header_parts = []
        if asset:
            header_parts.append(f"**Asset:** `{asset}`")
        if base_commit:
            display_commit = base_commit[:7] if len(base_commit) > 7 else base_commit
            header_parts.append(f"**Base Commit:** `{display_commit}`")
        if resolved_commit and resolved_commit != base_commit:
            header_parts.append(f"**VCS HEAD:** `{resolved_commit[:7]}`")
        if status:
            header_parts.append(f"**Status:** `{status.upper()}`")

        if header_parts:
            lines.append(" | ".join(header_parts) + "\n")

        if evidence and evidence.commit_message and not evidence.configuration_changes:
            lines.append(f"**Commit Message:** {evidence.commit_message}")
            if evidence.commit_author:
                lines.append(f"**Author:** {evidence.commit_author}\n")
            else:
                lines.append("")

        if explanation and explanation.summary:
            lines.append(f"**Summary:** {explanation.summary}\n")

        if explanation and explanation.causal_story:
            lines.append("#### Causal Chain & Rationale")
            lines.append(explanation.causal_story + "\n")

        if evidence and evidence.configuration_changes:
            lines.append("#### Proposed Parameter Changes")
            for ch in evidence.configuration_changes:
                lines.append(f"- **`{ch.path}`**: `{ch.old_value}` ➔ `{ch.new_value}`")
                if ch.reason:
                    lines.append(f"  *Reason:* {ch.reason}")
            lines.append("")

        if evidence and evidence.consistency_warnings:
            lines.append("#### ⚠️ Evidence Consistency Checks")
            for warning in evidence.consistency_warnings:
                lines.append(f"- {warning}")
            lines.append("")

        if evidence and evidence.expected_effect:
            lines.append(f"**Expected Effect:** {evidence.expected_effect}\n")

        if evidence and evidence.risks:
            lines.append("#### Risks & Considerations")
            for risk in evidence.risks:
                lines.append(f"- {risk}")
            lines.append("")

        if evidence and evidence.triggering_events:
            lines.append("#### Related Timeline Events")
            for event in evidence.triggering_events[:5]:
                ts = event.get("timestamp", "")
                title = event.get("title", "")
                lines.append(f"- **{ts}** — {title}")
            lines.append("")

        content = "\n".join(lines)
        presentation = DecisionInvestigationPresentation(
            blocks=[{"type": "markdown", "content": content}]
        )

        return {"presentation": presentation}
