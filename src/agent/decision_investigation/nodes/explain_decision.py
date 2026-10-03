from __future__ import annotations

from typing import Any

from src.agent.decision_investigation.models import DecisionEvidence, DecisionExplanation
from src.agent.decision_investigation.prompts import EXPLAIN_DECISION_PROMPT
from src.agent.decision_investigation.state import DecisionInvestigationState
from src.core.interfaces.llm_adapter import LlmAdapter


class ExplainDecisionNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: DecisionInvestigationState) -> dict[str, Any]:
        evidence = state.get("evidence") or DecisionEvidence()
        user_prompt = state.get("user_prompt", "")

        prompt = self._build_prompt(user_prompt, evidence)
        try:
            explanation: DecisionExplanation = self._llm.generate_structured(
                schema=DecisionExplanation,
                prompt=prompt,
                system_prompt=EXPLAIN_DECISION_PROMPT,
            )
        except Exception:
            explanation = self._build_fallback_explanation(evidence)

        return {"explanation": explanation}

    @staticmethod
    def _build_prompt(user_prompt: str, evidence: DecisionEvidence) -> str:
        lines = [
            f"USER QUERY: {user_prompt}",
            f"TARGET ASSET: {evidence.asset or 'General'}",
            f"BASE COMMIT: {evidence.base_commit or 'HEAD'} (Resolved: {evidence.resolved_commit_hash or 'N/A'})",
            f"APPROVAL STATUS: {evidence.approval_status or 'N/A'}",
        ]

        if evidence.proposal_rationale:
            lines.append(f"PROPOSAL RATIONALE: {evidence.proposal_rationale}")

        if evidence.expected_effect:
            lines.append(f"EXPECTED EFFECT: {evidence.expected_effect}")

        if evidence.configuration_changes:
            lines.append("PROPOSED CONFIGURATION CHANGES:")
            for ch in evidence.configuration_changes:
                lines.append(f"  - {ch.path}: {ch.old_value!r} -> {ch.new_value!r} (Reason: {ch.reason or 'N/A'})")

        if evidence.consistency_warnings:
            lines.append("CONSISTENCY WARNINGS:")
            for w in evidence.consistency_warnings:
                lines.append(f"  - {w}")

        if evidence.evidence_limitations:
            lines.append("EVIDENCE LIMITATIONS:")
            for lim in evidence.evidence_limitations:
                lines.append(f"  - {lim}")

        if evidence.risks:
            lines.append("RISKS:")
            for r in evidence.risks:
                lines.append(f"  - {r}")

        if evidence.triggering_events:
            lines.append("TIMELINE & TRIGGERING EVENTS:")
            for e in evidence.triggering_events:
                lines.append(f"  - [{e.get('timestamp')}] {e.get('title')}: {e.get('summary')}")

        return "\n".join(lines)

    @staticmethod
    def _build_fallback_explanation(evidence: DecisionEvidence) -> DecisionExplanation:
        summary = (
            f"Investigation for {evidence.asset or 'configuration'} (Base commit: {evidence.base_commit or 'HEAD'})."
        )
        causal_steps = []
        if evidence.triggering_events:
            causal_steps.append(f"1. **Triggering Events**: Detected {len(evidence.triggering_events)} related operational/timeline events.")
        if evidence.proposal_rationale:
            causal_steps.append(f"2. **Agent Rationale**: {evidence.proposal_rationale}")
        if evidence.configuration_changes:
            diff_summary = ", ".join(f"`{ch.path}` ({ch.old_value} -> {ch.new_value})" for ch in evidence.configuration_changes)
            causal_steps.append(f"3. **Proposed Adjustments**: {diff_summary}")
        if evidence.expected_effect:
            causal_steps.append(f"4. **Expected Effect**: {evidence.expected_effect}")

        if evidence.evidence_limitations:
            causal_steps.append(f"**Limitations**: {'; '.join(evidence.evidence_limitations)}")

        causal_story = "\n\n".join(causal_steps) if causal_steps else "The available evidence does not establish why this proposal was generated."
        return DecisionExplanation(
            summary=summary,
            causal_story=causal_story,
            key_factors=[ch.reason for ch in evidence.configuration_changes if ch.reason] or ["Configuration adjustment"],
        )
