from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.agent.runtime_debug.models import Evidence, RuntimeErrorEvent
from src.agent.runtime_debug.tools import RuntimeDebugToolbox


@runtime_checkable
class DebugPlaybook(Protocol):
    name: str

    def matches(self, event: RuntimeErrorEvent) -> bool:
        ...

    def investigate(self, event: RuntimeErrorEvent, toolbox: RuntimeDebugToolbox) -> list[Evidence]:
        ...
