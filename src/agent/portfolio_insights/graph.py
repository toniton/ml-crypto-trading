from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent.portfolio_insights.nodes.analyze_portfolio import AnalyzePortfolioNode
from src.agent.portfolio_insights.nodes.fetch_portfolio_data import FetchPortfolioDataNode
from src.agent.portfolio_insights.nodes.present_insights import PresentInsightsNode
from src.agent.portfolio_insights.nodes.understand_portfolio_query import UnderstandPortfolioQueryNode
from src.agent.portfolio_insights.state import PortfolioInsightsState
from src.core.interfaces.llm_adapter import LlmAdapter


class PortfolioInsightsGraph:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def build(self) -> CompiledStateGraph:
        builder = StateGraph(PortfolioInsightsState)
        builder.add_node("understand_portfolio_query", UnderstandPortfolioQueryNode(self._llm))
        builder.add_node("fetch_portfolio_data", FetchPortfolioDataNode(self._llm))
        builder.add_node("analyze_portfolio", AnalyzePortfolioNode(self._llm))
        builder.add_node("present_insights", PresentInsightsNode())

        builder.add_edge(START, "understand_portfolio_query")
        builder.add_edge("understand_portfolio_query", "fetch_portfolio_data")
        builder.add_edge("fetch_portfolio_data", "analyze_portfolio")
        builder.add_edge("analyze_portfolio", "present_insights")
        builder.add_edge("present_insights", END)
        return builder.compile()
