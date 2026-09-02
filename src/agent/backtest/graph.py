from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent.backtest.nodes.analyze_result import AnalyzeResultNode
from src.agent.backtest.nodes.build_request import BuildBacktestRequestNode
from src.agent.backtest.nodes.present_result import PresentResultNode
from src.agent.backtest.nodes.run_backtest import RunBacktestNode
from src.agent.backtest.nodes.understand_request import UnderstandBacktestRequestNode
from src.agent.backtest.nodes.validate_request import ValidateBacktestRequestNode
from src.agent.backtest.state import BacktestAgentState
from src.core.interfaces.llm_adapter import LlmAdapter


class BacktestGraph:
    """Orchestrates a multi-step backtest workflow.

    The graph interprets the user's request, resolves data/time, validates,
    executes via the registered backtest tool, analyzes the result and presents it.
    It contains no backtesting logic itself.
    """

    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    @staticmethod
    def route_after_validation(state: BacktestAgentState) -> str:
        validation = state.get("validation")
        if validation and not validation.valid:
            return "present"
        return "run"

    def build(self) -> CompiledStateGraph:
        builder = StateGraph(BacktestAgentState)
        builder.add_node("understand_request", UnderstandBacktestRequestNode(self._llm))
        builder.add_node("build_request", BuildBacktestRequestNode())
        builder.add_node("validate_request", ValidateBacktestRequestNode())
        builder.add_node("run_backtest", RunBacktestNode(self._llm))
        builder.add_node("analyze_result", AnalyzeResultNode())
        builder.add_node("present_result", PresentResultNode())


        builder.add_edge(START, "understand_request")
        builder.add_edge("understand_request", "build_request")
        builder.add_edge("build_request", "validate_request")
        builder.add_conditional_edges(
            "validate_request",
            self.route_after_validation,
            {"present": "present_result", "run": "run_backtest"},
        )
        builder.add_edge("run_backtest", "analyze_result")
        builder.add_edge("analyze_result", "present_result")
        builder.add_edge("present_result", END)
        return builder.compile()
