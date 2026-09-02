from __future__ import annotations

from typing import List, TypedDict

from src.agent.router.models import AgentRoute
from src.core.interfaces.llm_adapter import ChatTurn


class RouterState(TypedDict, total=False):
    user_prompt: str
    history: List[ChatTurn]
    route: AgentRoute
    agent: str
