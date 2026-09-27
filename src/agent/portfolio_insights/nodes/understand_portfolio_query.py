from __future__ import annotations

from src.agent.portfolio_insights.models import PortfolioQueryIntent
from src.agent.portfolio_insights.prompts import UNDERSTAND_PORTFOLIO_QUERY_PROMPT
from src.agent.portfolio_insights.state import PortfolioInsightsState
from src.core.interfaces.llm_adapter import LlmAdapter


class UnderstandPortfolioQueryNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: PortfolioInsightsState) -> dict:
        prompt = self._build_prompt(state)
        query_intent: PortfolioQueryIntent = self._llm.generate_structured(
            schema=PortfolioQueryIntent,
            prompt=prompt,
            system_prompt=UNDERSTAND_PORTFOLIO_QUERY_PROMPT,
        )
        return {"portfolio_query": query_intent}

    @staticmethod
    def _build_prompt(state: PortfolioInsightsState) -> str:
        lines = ["USER PROMPT", state["user_prompt"]]
        history = state.get("history", [])
        if history:
            lines.append("\nCONVERSATION HISTORY")
            for turn in history[-4:]:
                lines.append(f"{turn.role}: {turn.content}")
        return "\n".join(lines)
