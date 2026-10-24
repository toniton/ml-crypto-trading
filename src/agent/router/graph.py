from __future__ import annotations

from typing import Callable, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.core.interfaces.llm_adapter import LlmAdapter
from src.agent.operational.collector import (
    HealthMonitorContextCollector,
    OperationalContextCollectorProtocol,
)
from src.agent.router.models import AgentIntent
from src.agent.router.nodes.extract_references import ExtractReferencesNode
from src.agent.router.nodes.operational_status import OperationalStatusNode
from src.agent.router.nodes.route import RouteNode
from src.agent.router.nodes.understand_goal import UnderstandGoalNode
from src.agent.router.state import RouterState
from src.trading.health.health_monitor import HealthMonitor


class RouterGraph:
    def __init__(
            self,
            llm: LlmAdapter,
            resolve: Callable[[AgentIntent], str] = lambda intent: intent.value,
            collector: Optional[OperationalContextCollectorProtocol] = None,
            health_monitor: Optional[HealthMonitor] = None,
    ):
        self._llm = llm
        self._resolve = resolve
        if collector is not None:
            self._collector = collector
        else:
            self._collector = HealthMonitorContextCollector(health_monitor)

    def build(self) -> CompiledStateGraph:
        builder = StateGraph(RouterState)
        builder.add_node("extract_references", ExtractReferencesNode())
        builder.add_node("operational_status", OperationalStatusNode(self._collector))
        builder.add_node("understand_goal", UnderstandGoalNode(self._llm))
        builder.add_node("route", RouteNode(self._resolve))

        builder.add_edge(START, "extract_references")
        builder.add_edge("extract_references", "operational_status")
        builder.add_edge("operational_status", "understand_goal")
        builder.add_edge("understand_goal", "route")
        builder.add_edge("route", END)
        return builder.compile()
