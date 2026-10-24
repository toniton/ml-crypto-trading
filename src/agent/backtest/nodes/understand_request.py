from __future__ import annotations

from src.agent.backtest.models import BacktestAgentRequest
from src.agent.backtest.prompts import BACKTEST_REQUEST_PROMPT
from src.agent.backtest.state import BacktestAgentState
from src.core.interfaces.llm_adapter import LlmAdapter


class UnderstandBacktestRequestNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: BacktestAgentState) -> dict:
        request: BacktestAgentRequest = self._llm.generate_structured(
            schema=BacktestAgentRequest,
            prompt=self._build_prompt(state),
            system_prompt=BACKTEST_REQUEST_PROMPT,
        )
        return {"backtest_request": request}

    @staticmethod
    def _build_prompt(state: BacktestAgentState) -> str:
        lines = ["USER REQUEST", state["user_prompt"]]
        route = state.get("request")
        if route and route.goal:
            lines.append("EXTRACTED GOAL")
            lines.append(f"objective: {route.goal.objective}")
            if route.goal.target_asset:
                lines.append(f"target_asset: {route.goal.target_asset}")
        if route and route.references and route.references.asset:
            lines.append(f"referenced_asset: {route.references.asset}")
        history_turns = state.get("history") or []
        if history_turns:
            lines.append("CONVERSATION HISTORY")
            lines.extend(f"{turn.role}: {turn.content}" for turn in history_turns)
        return "\n".join(lines)
