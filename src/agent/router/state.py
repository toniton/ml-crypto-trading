from __future__ import annotations

from typing import TypedDict

from src.agent.router.models import AgentRoute


class RouterState(TypedDict, total=False):
    user_prompt: str
    route: AgentRoute
    agent: str
