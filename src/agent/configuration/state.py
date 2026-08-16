from __future__ import annotations

from typing import TypedDict

from src.agent.router.models import AgentRoute
from src.agent.configuration.models import (
    ConfigurationPresentation,
    ConfigurationProposal,
    ValidationResult,
)


class ConfigurationAgentState(TypedDict, total=False):
    user_prompt: str
    request: AgentRoute
    proposal: ConfigurationProposal
    validation: ValidationResult
    catalog_context: str
    presentation: ConfigurationPresentation
    proposal_attempts: int
