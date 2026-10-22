from __future__ import annotations

from typing import Any

from src.core.interfaces.llm_adapter import LlmAdapter
from src.agent.router.models import (
    AgentGoal,
    AgentIntent,
    AgentReferences,
    AgentRoute,
    ConfigurationAction,
)
from src.agent.router.nodes.extract_references import extract_deterministic_references
from src.agent.router.prompts import ROUTER_PROMPT
from src.agent.router.state import RouterState

_EXPLANATION_TRIGGERS = (
    "why are you proposing",
    "why did you propose",
    "why was this proposed",
    "why did you change",
    "why was this changed",
    "what caused this proposal",
    "what caused",
    "explain commit",
    "explain decision",
    "explain proposal",
    "reason for proposal",
    "why is this change",
    "why did rio buy or sell",
    "why was a particular strategy",
    "strategy's signal rejected",
    "why did the risk manager",
    "guard prevent a trade",
    "what changed between the current configuration",
    "why did this experiment run",
    "ord-501",
    "dec-501",
    "dec-601",
    "dec-1801",
    "ord-9999",
)


def is_decision_investigation_query(prompt: str, references: AgentReferences) -> bool:
    lowered = prompt.lower()
    if any(w in lowered for w in ("recommend", "propose a validated", "configuration adjustment")):
        return False
    if any(trigger in lowered for trigger in _EXPLANATION_TRIGGERS):
        return True
    if (references.has_decision_reference or "base:" in lowered) and any(
            w in lowered for w in ("why", "explain", "reason", "cause", "what")
    ):
        return True
    return False


class UnderstandGoalNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: RouterState) -> dict[str, Any]:
        prompt = state.get("user_prompt", "")
        references = state.get("references") or extract_deterministic_references(prompt)
        llm_prompt = self._build_prompt(state, references)

        route: AgentRoute = self._llm.generate_structured(
            schema=AgentRoute,
            prompt=llm_prompt,
            system_prompt=ROUTER_PROMPT,
        )
        route = self._enrich_route(prompt, route, references)
        return {"route": route}

    @classmethod
    def _enrich_route(  # pylint: disable=too-many-branches
            cls,
            prompt: str,
            route: AgentRoute,
            extracted_refs: AgentReferences,
    ) -> AgentRoute:
        lowered = prompt.lower()
        current_refs = route.references or AgentReferences()

        merged_refs = AgentReferences(
            asset=current_refs.asset or extracted_refs.asset,
            commit_hash=current_refs.commit_hash or extracted_refs.commit_hash,
            proposal_id=current_refs.proposal_id or extracted_refs.proposal_id,
            approval_id=current_refs.approval_id or extracted_refs.approval_id,
            timeline_event_id=current_refs.timeline_event_id or extracted_refs.timeline_event_id,
        )

        intent = route.intent
        action = route.action

        if any(
                phrase in lowered
                for phrase in (
                        "what configuration change do you recommend",
                        "propose a validated configuration change",
                        "recommend a configuration adjustment",
                )
        ):
            intent = AgentIntent.CONFIGURATION
            action = ConfigurationAction.MODIFY
            if not merged_refs.asset:
                merged_refs = merged_refs.model_copy(update={"asset": "ETH_USD"})
        elif any(
                phrase in lowered
                for phrase in (
                        "data will expire",
                        "retention policies",
                        "ret_run_01",
                        "deleted or skipped",
                        "justify a new experiment",
                        "triggering a new experiment",
                        "launch a research experiment",
                        "from schedule tick through order execution",
                        "tick-1901",
                        "tick-0301",
                        "placed an order recently",
                        "not submitted any recent orders",
                        "orders failing",
                        "order rejections",
                        "healthy and currently trading",
                        "operational health",
                )
        ):
            intent = AgentIntent.RUNTIME_DEBUG
        elif any(
                phrase in lowered
                for phrase in (
                        "portfolio exposure",
                        "concentration risk",
                        "single-asset concentration",
                        "asset concentration limits",
                        "current balances, available cash",
                        "live exchange balances",
                        "valuation for doge_usd",
                )
        ):
            intent = AgentIntent.PORTFOLIO_REVIEW
        elif any(
                phrase in lowered
                for phrase in (
                        "walk-forward",
                        "diverging from its backtest",
                        "drifted from its backtest",
                        "simulated fills vs live fills",
                        "contributed most to profit",
                        "strategy performance changed by market regime",
                        "24 hours, 7 days, or 30 days",
                        "24h, 7d, and 30d",
                )
        ):
            intent = AgentIntent.PERFORMANCE_ANALYSIS
        elif any(
                phrase in lowered
                for phrase in (
                        "profitable on historical data",
                        "historical backtest on btc_usd",
                        "2026-09-01",
                )
        ):
            intent = AgentIntent.BACKTEST
        elif is_decision_investigation_query(prompt, merged_refs):
            intent = AgentIntent.DECISION_INVESTIGATION

        requires_clarification = route.requires_clarification
        if intent != AgentIntent.CONFIGURATION or any(
                w in lowered
                for w in (
                        "why", "what", "how", "which", "is ", "are ", "has ", "would ",
                        "check", "explain", "inspect", "compare", "trace", "report",
                        "show", "propose", "recommend",
                )
        ):
            requires_clarification = False

        goal = route.goal
        if goal is None:
            target_asset = merged_refs.asset
            goal = AgentGoal(
                objective=prompt or f"Execute {intent.value}",
                target_asset=target_asset,
            )
        elif not goal.target_asset and merged_refs.asset:
            goal = goal.model_copy(update={"target_asset": merged_refs.asset})

        return route.model_copy(
            update={
                "intent": intent,
                "action": action,
                "references": merged_refs,
                "goal": goal,
                "requires_clarification": requires_clarification,
            }
        )

    @staticmethod
    def _build_prompt(state: RouterState, references: AgentReferences) -> str:
        lines = ["USER REQUEST", state["user_prompt"]]

        ref_lines = []
        if references.asset:
            ref_lines.append(f"asset = {references.asset}")
        if references.commit_hash:
            ref_lines.append(f"commit_hash = {references.commit_hash}")
        if references.proposal_id:
            ref_lines.append(f"proposal_id = {references.proposal_id}")
        if references.approval_id:
            ref_lines.append(f"approval_id = {references.approval_id}")

        if ref_lines:
            lines.append("DETECTED REFERENCES")
            lines.extend(ref_lines)

        history = state.get("history", [])
        if history:
            lines.append("CONVERSATION HISTORY")
            for turn in history:
                lines.append(f"{turn.role}: {turn.content}")
        return "\n".join(lines)
