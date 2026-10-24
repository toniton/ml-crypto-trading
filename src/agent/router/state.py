from __future__ import annotations

from typing import List, Optional, TypedDict

from src.agent.operational.models import OperationalContext
from src.agent.router.models import AgentReferences, AgentRoute
from src.core.interfaces.llm_adapter import ChatTurn


class RouterState(TypedDict, total=False):
    user_prompt: str
    history: List[ChatTurn]
    references: AgentReferences
    operational_context: Optional[OperationalContext]
    route: AgentRoute
    agent: str
