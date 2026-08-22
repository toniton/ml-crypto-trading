from __future__ import annotations

from typing import List, TypedDict

from src.core.interfaces.llm_adapter import ChatTurn
from src.agent.router.models import AgentRoute
from src.agent.configuration.models import (
    ConfigurationPresentation,
    ConfigurationProposal,
    ValidationResult,
)


class ConfigurationAgentState(TypedDict, total=False):
    user_prompt: str
    request: AgentRoute
    history: List[ChatTurn]
    proposal: ConfigurationProposal
    validation: ValidationResult
    catalog_context: str
    presentation: ConfigurationPresentation
    proposal_attempts: int
