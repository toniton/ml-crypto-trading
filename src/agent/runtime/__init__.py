"""Agent runtime primitives shared by all specialized agents."""

from __future__ import annotations

from src.agent.runtime.agent import AgentDefinition
from src.agent.runtime.registry import AgentRegistry

__all__ = ["AgentDefinition", "AgentRegistry"]
