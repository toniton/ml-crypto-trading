from __future__ import annotations

from typing import Callable

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.core.interfaces.llm_adapter import LlmAdapter
from src.agent.router.models import AgentIntent
from src.agent.router.nodes.route import RouteNode
from src.agent.router.nodes.understand_goal import UnderstandGoalNode
from src.agent.router.state import RouterState


class RouterGraph:
    def __init__(
            self,
            llm: LlmAdapter,
            resolve: Callable[[AgentIntent], str] = lambda intent: intent.value,
    ):
        self._llm = llm
        self._resolve = resolve

    def build(self) -> CompiledStateGraph:
        builder = StateGraph(RouterState)
        builder.add_node("understand_goal", UnderstandGoalNode(self._llm))
        builder.add_node("route", RouteNode(self._resolve))
        builder.add_edge(START, "understand_goal")
        builder.add_edge("understand_goal", "route")
        builder.add_edge("route", END)
        return builder.compile()
