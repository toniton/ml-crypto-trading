from __future__ import annotations

from typing import Any

from src.core.interfaces.llm_adapter import LlmAdapter
from src.agent.router.models import AgentGoal, AgentIntent, AgentReferences, AgentRoute
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
)


def is_decision_investigation_query(prompt: str, references: AgentReferences) -> bool:
    lowered = prompt.lower()
    if any(trigger in lowered for trigger in _EXPLANATION_TRIGGERS):
        return True
    if (references.has_decision_reference or "base:" in lowered) and any(w in lowered for w in ("why", "explain", "reason", "cause", "what")):
        return True
    return False


from src.agent.router.nodes.extract_references import extract_deterministic_references


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
    def _enrich_route(cls, prompt: str, route: AgentRoute, extracted_refs: AgentReferences) -> AgentRoute:
        current_refs = route.references or AgentReferences()

        merged_refs = AgentReferences(
            asset=current_refs.asset or extracted_refs.asset,
            commit_hash=current_refs.commit_hash or extracted_refs.commit_hash,
            proposal_id=current_refs.proposal_id or extracted_refs.proposal_id,
            approval_id=current_refs.approval_id or extracted_refs.approval_id,
            timeline_event_id=current_refs.timeline_event_id or extracted_refs.timeline_event_id,
        )

        intent = route.intent
        if is_decision_investigation_query(prompt, merged_refs):
            intent = AgentIntent.DECISION_INVESTIGATION

        goal = route.goal
        if goal is None and intent == AgentIntent.DECISION_INVESTIGATION:
            goal = AgentGoal(
                objective=f"Investigate decision/proposal for {merged_refs.asset or 'configuration'}",
                target_asset=merged_refs.asset,
            )

        return route.model_copy(
            update={
                "intent": intent,
                "references": merged_refs,
                "goal": goal,
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
