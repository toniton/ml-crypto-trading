from __future__ import annotations

from typing import List, TypedDict

from api.interfaces.backtest_request import BacktestRequest
from src.agent.backtest.models import (
    BacktestAgentRequest,
    BacktestPresentation,
    BacktestQuality,
    BacktestValidation,
)
from src.agent.router.models import AgentRoute
from src.backtest.domain.metrics import BacktestSummary
from src.backtest.domain.result import BacktestResult
from src.core.interfaces.llm_adapter import ChatTurn


class BacktestAgentState(TypedDict, total=False):
    user_prompt: str
    request: AgentRoute
    history: List[ChatTurn]
    backtest_request: BacktestAgentRequest
    resolved_request: BacktestRequest
    validation: BacktestValidation
    result: BacktestResult
    summary: BacktestSummary
    quality: BacktestQuality
    error: str
    presentation: BacktestPresentation
