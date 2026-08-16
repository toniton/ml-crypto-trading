from __future__ import annotations

from typing import Iterable, Optional

from src.agent.router.models import AgentIntent
from src.agent.runtime.agent import AgentDefinition
from src.core.registry import Registry


class AgentRegistry(Registry[AgentIntent, AgentDefinition]):
    def __init__(self, definitions: Iterable[AgentDefinition]):
        super().__init__()
        self._definitions: dict[str, AgentDefinition] = {
            definition.name: definition for definition in definitions
        }

    def register(self, intent: AgentIntent, name: str) -> None:
        if name not in self._definitions:
            raise KeyError(f"Unknown agent '{name}' cannot be registered for intent '{intent.value}'")
        self.replace(intent, self._definitions[name])

    def agent_name_for(self, intent: AgentIntent) -> str:
        return self.get(intent).name

    def get(self, intent: AgentIntent) -> AgentDefinition:
        definition = self.find(intent)
        if definition is None:
            definition = self.find(AgentIntent.GENERAL)
            if definition is None:
                return self._definitions["general"]
        return definition

    def get_by_name(self, name: str) -> Optional[AgentDefinition]:
        return self._definitions.get(name)

    @property
    def definitions(self) -> list[AgentDefinition]:
        return list(self._definitions.values())

    def has(self, name: str) -> bool:
        return name in self._definitions
