from __future__ import annotations

from src.agent.backtest.state import BacktestAgentState
from src.core.interfaces.llm_adapter import LlmAdapter


class RunBacktestNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: BacktestAgentState) -> dict:
        resolved = state["resolved_request"]
        tool = self._llm.get_tool("run_backtest")
        if tool is None or not hasattr(tool, "backtest_service"):
            return {"error": "Backtest tool is not available"}
        try:
            service = tool.backtest_service
            result = service.run(resolved)
            summary = service.summary(result.session_id)
            return {"result": result, "summary": summary}
        except Exception as exc:  # pylint: disable=broad-except
            return {"error": str(exc)}
