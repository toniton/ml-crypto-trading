"""AgentDefinition: the registered, self-describing unit of the agent platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from langgraph.graph.state import CompiledStateGraph


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    description: str
    graph: Optional[CompiledStateGraph] = None
    presentation_node: Optional[str] = None
    capabilities: frozenset[str] = field(default_factory=frozenset)
