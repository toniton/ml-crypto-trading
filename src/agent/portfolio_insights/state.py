from __future__ import annotations

from typing import Optional, TypedDict

from src.agent.portfolio_insights.models import (
    PortfolioAnalysisResult,
    PortfolioInsightsPresentation,
    PortfolioQueryIntent,
)
from src.agent.router.models import AgentRoute
from src.core.interfaces.llm_adapter import ChatTurn


class PortfolioInsightsState(TypedDict, total=False):
    user_prompt: str
    request: AgentRoute
    history: list[ChatTurn]
    portfolio_query: Optional[PortfolioQueryIntent]
    portfolio_data: Optional[str]
    analysis: Optional[PortfolioAnalysisResult]
    presentation: Optional[PortfolioInsightsPresentation]
