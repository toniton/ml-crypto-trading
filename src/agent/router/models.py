from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AgentIntent(str, Enum):
    CONFIGURATION = "configuration"
    PERFORMANCE_ANALYSIS = "performance_analysis"
    RISK_ANALYSIS = "risk_analysis"
    MARKET_ANALYSIS = "market_analysis"
    REPORTING = "reporting"
    SYSTEM_HELP = "system_help"
    GENERAL = "general"


class AgentGoal(BaseModel):
    objective: str = Field(description="One sentence describing what the user wants to achieve.")
    target_asset: Optional[str] = Field(
        default=None,
        description=(
            "The asset symbol (e.g. BTC_USD) the user explicitly scoped their request to, "
            "or null when the request is not asset-specific."
        ),
    )
    desired_outcomes: list[str] = Field(
        default_factory=list,
        description="Observable conditions the user wants to become true.",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Boundaries the user explicitly does not want to cross.",
    )
    ambiguities: list[str] = Field(
        default_factory=list,
        description="Unclear aspects that would change how the agent should act if resolved.",
    )


class AgentRoute(BaseModel):
    intent: AgentIntent = Field(
        default=AgentIntent.GENERAL,
        description="Which registered agent should handle this request.",
    )
    goal: Optional[AgentGoal] = Field(
        default=None,
        description="The structured goal, populated when the intent needs one.",
    )
    requires_clarification: bool = Field(
        default=False,
        description="True when the request is too vague to act on without asking the user.",
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="The question to ask the user when requires_clarification is true.",
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="A short justification for the chosen intent (for logs, not user-facing routing).",
    )
