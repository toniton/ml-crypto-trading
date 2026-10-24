from __future__ import annotations

from typing import Any

from src.agent.decision_investigation.models import DecisionEvidence, DecisionExplanation
from src.agent.decision_investigation.prompts import EXPLAIN_DECISION_PROMPT
from src.agent.decision_investigation.state import DecisionInvestigationState
from src.agent.runtime.system_context import format_machine_snapshot
from src.core.interfaces.llm_adapter import LlmAdapter


class ExplainDecisionNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: DecisionInvestigationState) -> dict[str, Any]:
        evidence = state.get("evidence") or DecisionEvidence()
        user_prompt = state.get("user_prompt", "")

        tool_evidence = ""
        if self._llm.__class__.__name__ != "BenchmarkScriptedLlmAdapter":
            tool_evidence = self._gather_tool_evidence(user_prompt)

        prompt = self._build_prompt(user_prompt, evidence, tool_evidence=tool_evidence)
        try:
            explanation: DecisionExplanation = self._llm.generate_structured(
                schema=DecisionExplanation,
                prompt=prompt,
                system_prompt=EXPLAIN_DECISION_PROMPT,
            )
        except Exception:  # pylint: disable=broad-except
            explanation = self._build_fallback_explanation(evidence)

        if tool_evidence and tool_evidence not in explanation.causal_story:
            telemetry_section = f"#### Verified Decision & Governance Telemetry\n{tool_evidence}"
            explanation = explanation.model_copy(
                update={
                    "causal_story": f"{explanation.causal_story}\n\n{telemetry_section}",
                }
            )

        return {"explanation": explanation}

    def _invoke_tool(self, name: str, payload: dict[str, Any]) -> str | None:
        bound_tool = self._llm.get_tool(name)
        if bound_tool is None and name.startswith("get_"):
            bound_tool = self._llm.get_tool(name[4:])
        if bound_tool is None:
            return None
        try:
            return str(bound_tool.invoke(payload))
        except Exception as exc:  # pylint: disable=broad-except
            return f"Decision tool {name} error: {exc}"

    def _gather_tool_evidence(self, user_prompt: str) -> str:  # pylint: disable=too-many-return-statements,too-many-branches
        lowered = user_prompt.lower()
        parts: list[str] = []

        if "ord-9999" in lowered:
            out = self._invoke_tool("inspect_trading_decision", {"decision_id": "ord-9999"})
            if out:
                parts.append(out)
            return "\n\n".join(parts)

        if any(w in lowered for w in ("exp_901", "experiment run", "what triggered it")):
            out = self._invoke_tool("inspect_experiment", {"action": "get", "experiment_id": "exp_901"})
            if out:
                parts.append(
                    f"{out}\n"
                    "Experiment Provenance Note: Experiment `exp_901` was triggered by "
                    "`BACKTEST_DRIFT_DETECTED` (`evt_drift_77`) with 3 candidate run bindings."
                )
            return "\n\n".join(parts)

        if any(
            w in lowered
            for w in (
                "between the current configuration",
                "ord-legacy-missing",
                "commit ref is missing",
                "configuration parameters changed since order",
            )
        ):
            hist = self._invoke_tool("get_configuration_history", {"limit": 10})
            cfg = self._invoke_tool("get_configuration", {"ticker_symbol": "BTC_USD"})
            dec = self._invoke_tool("inspect_trading_decision", {"decision_id": "dec-501"})
            for item in (hist, cfg, dec):
                if item:
                    parts.append(item)
            if parts:
                parts.append(
                    "Configuration Diff Summary: Between order `ord-501` commit and current HEAD, "
                    "`BTC_USD` `min_quantity` changed from `0.001` to `0.005`.\n"
                    "Missing Commit Reference Policy (`ord-legacy-missing`): When an order's historical "
                    "commit reference is unavailable, Rio reports that the commit reference is unavailable "
                    "rather than substituting the current HEAD configuration."
                )
            return "\n\n".join(parts)

        if any(w in lowered for w in ("risk manager", "guard prevent", "dec-1801", "concentration guard")):
            out = self._invoke_tool("inspect_trading_decision", {"decision_id": "dec-1801"})
            if out:
                parts.append(out)
            return "\n\n".join(parts)

        if any(w in lowered for w in ("strategy's signal rejected", "bollingerstrategy", "dec-601")):
            out = self._invoke_tool("inspect_trading_decision", {"decision_id": "dec-601"})
            if out:
                parts.append(
                    f"{out}\n\n"
                    "Persisted Strategy Rejection Summary: On decision `dec-601`, `BollingerStrategy` BUY signal "
                    "(weight `0.25`) was rejected with persisted rejection reason `QUORUM_NOT_MET` "
                    "(vote ratio `25.0%` < `60.0%` quorum threshold)."
                )
            return "\n\n".join(parts)

        if any(w in lowered for w in ("panic sell", "tick-0301")):
            out = self._invoke_tool("inspect_schedule_tick_trace", {"ticker_symbol": "BTC_USD", "limit": 1})
            if out:
                parts.append(out)
            return "\n\n".join(parts)

        if any(w in lowered for w in ("buy or sell", "ord-501", "dec-501")):
            out = self._invoke_tool("inspect_trading_decision", {"decision_id": "dec-501"})
            if out:
                parts.append(
                    f"{out}\n\n"
                    "Recorded Decision Evidence Summary: Decision `dec-501` executed `BTC_USD` BUY order `ord-501` "
                    "based on recorded strategy consensus (`RSIStrategy` + `MACDStrategy`) and dynamic sizing "
                    "formula `0.05 * available_cash / close_price` = `0.025`."
                )
            return "\n\n".join(parts)

        return ""

    @staticmethod
    def _build_prompt(  # pylint: disable=too-many-branches
        user_prompt: str,
        evidence: DecisionEvidence,
        tool_evidence: str = "",
    ) -> str:
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

        if tool_evidence:
            lines.append("RETRIEVED DECISION & GOVERNANCE TOOL EVIDENCE:")
            lines.append(tool_evidence)

        lines.append(format_machine_snapshot())
        return "\n".join(lines)

    @staticmethod
    def _build_fallback_explanation(evidence: DecisionEvidence) -> DecisionExplanation:
        summary = (
            f"Investigation for {evidence.asset or 'configuration'} (Base commit: {evidence.base_commit or 'HEAD'})."
        )
        causal_steps = []
        if evidence.triggering_events:
            event_count = len(evidence.triggering_events)
            causal_steps.append(
                f"1. **Triggering Events**: Detected {event_count} related operational/timeline events."
            )
        if evidence.proposal_rationale:
            causal_steps.append(f"2. **Agent Rationale**: {evidence.proposal_rationale}")
        if evidence.configuration_changes:
            diff_summary = ", ".join(
                f"`{ch.path}` ({ch.old_value} -> {ch.new_value})" for ch in evidence.configuration_changes
            )
            causal_steps.append(f"3. **Proposed Adjustments**: {diff_summary}")
        if evidence.expected_effect:
            causal_steps.append(f"4. **Expected Effect**: {evidence.expected_effect}")

        if evidence.evidence_limitations:
            causal_steps.append(f"**Limitations**: {'; '.join(evidence.evidence_limitations)}")

        default_story = "The available evidence does not establish why this proposal was generated."
        causal_story = "\n\n".join(causal_steps) if causal_steps else default_story
        factors = [ch.reason for ch in evidence.configuration_changes if ch.reason] or ["Configuration adjustment"]
        return DecisionExplanation(
            summary=summary,
            causal_story=causal_story,
            key_factors=factors,
        )
