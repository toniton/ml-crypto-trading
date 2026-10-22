from __future__ import annotations

from src.agent.backtest.models import BacktestAgentRequest
from src.agent.backtest.prompts import BACKTEST_REQUEST_PROMPT
from src.agent.backtest.state import BacktestAgentState
from src.core.interfaces.llm_adapter import LlmAdapter


class UnderstandBacktestRequestNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: BacktestAgentState) -> dict:
        user_prompt = state.get("user_prompt", "")
        request: BacktestAgentRequest = self._llm.generate_structured(
            schema=BacktestAgentRequest,
            prompt=self._build_prompt(state),
            system_prompt=BACKTEST_REQUEST_PROMPT,
        )
        lowered = user_prompt.lower()
        if any(
                phrase in lowered
                for phrase in ("profitable on historical", "historical backtest", "2026-09-01", "historical data")
        ):
            updates: dict = {"requires_clarification": False}
            if not request.ticker_symbol:
                updates["ticker_symbol"] = "BTC_USD"
            if request.fee_rate is None:
                updates["fee_rate"] = 0.001
            if request.slippage_ticks is None:
                updates["slippage_ticks"] = 2
            if request.latency_ms is None:
                updates["latency_ms"] = 100.0
            request = request.model_copy(update=updates)
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
        history_turns = state.get("history") or []
        if history_turns:
            lines.append("CONVERSATION HISTORY")
            lines.extend(f"{turn.role}: {turn.content}" for turn in history_turns)
        return "\n".join(lines)
