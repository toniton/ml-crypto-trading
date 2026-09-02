from __future__ import annotations

from typing import Optional, TypedDict

from src.agent.performance_analysis.models import AnalyticsPresentation, MetricQueryIntent
from src.agent.router.models import AgentRoute
from src.core.interfaces.llm_adapter import ChatTurn


class PerformanceAnalysisState(TypedDict, total=False):
    user_prompt: str
    request: Optional[AgentRoute]
    history: list[ChatTurn]
    query_intent: Optional[MetricQueryIntent]
    metric_data: Optional[str]
    analysis_summary: Optional[str]
    presentation: Optional[AnalyticsPresentation]
