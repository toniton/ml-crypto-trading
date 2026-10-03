from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AgentIntent(str, Enum):
    CONFIGURATION = "configuration"
    DECISION_INVESTIGATION = "decision_investigation"
    PERFORMANCE_ANALYSIS = "performance_analysis"
    PORTFOLIO_REVIEW = "portfolio_review"
    RISK_ANALYSIS = "risk_analysis"
    MARKET_ANALYSIS = "market_analysis"
    REPORTING = "reporting"
    SYSTEM_HELP = "system_help"
    BACKTEST = "backtest"
    RUNTIME_DEBUG = "runtime_debug"
    GENERAL = "general"


class ConfigurationAction(str, Enum):
    VIEW = "view"
    MODIFY = "modify"


class AgentReferences(BaseModel):
    asset: Optional[str] = Field(
        default=None,
        description="Asset symbol (e.g. CRO_USD, BTC_USD) referenced in the request.",
    )
    commit_hash: Optional[str] = Field(
        default=None,
        description="Commit hash or short hash (e.g. 235f666) referenced in the request.",
    )
    proposal_id: Optional[str] = Field(
        default=None,
        description="Proposal identifier referenced in the request.",
    )
    approval_id: Optional[str] = Field(
        default=None,
        description="Approval identifier referenced in the request.",
    )
    timeline_event_id: Optional[str] = Field(
        default=None,
        description="Timeline event identifier referenced in the request.",
    )

    @property
    def has_decision_reference(self) -> bool:
        return bool(self.commit_hash or self.proposal_id or self.approval_id or self.timeline_event_id)


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
    action: ConfigurationAction = Field(
        default=ConfigurationAction.MODIFY,
        description="For configuration requests: whether the user wants to view the config or modify it.",
    )
    goal: Optional[AgentGoal] = Field(
        default=None,
        description="The structured goal, populated when the intent needs one.",
    )
    references: AgentReferences = Field(
        default_factory=AgentReferences,
        description="Structured entities extracted from the query (e.g. asset, commit_hash, proposal_id).",
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
