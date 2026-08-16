from __future__ import annotations

from src.core.interfaces.llm_adapter import LlmAdapter
from src.agent.router.models import AgentRoute
from src.agent.router.prompts import ROUTER_PROMPT
from src.agent.router.state import RouterState


class UnderstandGoalNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: RouterState) -> dict:
        route: AgentRoute = self._llm.generate_structured(
            schema=AgentRoute,
            prompt=state["user_prompt"],
            system_prompt=ROUTER_PROMPT,
        )
        return {"route": route}
