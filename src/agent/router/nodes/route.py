from __future__ import annotations

from typing import Callable

from src.agent.router.models import AgentIntent
from src.agent.router.state import RouterState


class RouteNode:
    def __init__(self, resolve: Callable[[AgentIntent], str]):
        self._resolve = resolve

    def __call__(self, state: RouterState) -> dict:
        route = state["route"]
        return {"agent": self._resolve(route.intent)}
