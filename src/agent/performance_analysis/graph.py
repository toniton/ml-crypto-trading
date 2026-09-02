from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent.performance_analysis.nodes.analyze_metrics import AnalyzeMetricsNode
from src.agent.performance_analysis.nodes.fetch_metrics import FetchMetricsNode
from src.agent.performance_analysis.nodes.present_analysis import PresentAnalysisNode
from src.agent.performance_analysis.nodes.understand_query import UnderstandMetricQueryNode
from src.agent.performance_analysis.state import PerformanceAnalysisState
from src.core.interfaces.llm_adapter import LlmAdapter


class PerformanceAnalysisGraph:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def build(self) -> CompiledStateGraph:
        builder = StateGraph(PerformanceAnalysisState)
        builder.add_node("understand_query", UnderstandMetricQueryNode(self._llm))
        builder.add_node("fetch_metrics", FetchMetricsNode(self._llm))
        builder.add_node("analyze_metrics", AnalyzeMetricsNode(self._llm))
        builder.add_node("present_analysis", PresentAnalysisNode())

        builder.add_edge(START, "understand_query")
        builder.add_edge("understand_query", "fetch_metrics")
        builder.add_edge("fetch_metrics", "analyze_metrics")
        builder.add_edge("analyze_metrics", "present_analysis")
        builder.add_edge("present_analysis", END)
        return builder.compile()
