from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

from src.agent.configuration.models import ConfigChange
from src.agent.router.models import AgentGoal


class DecisionEvidence(BaseModel):
    asset: Optional[str] = Field(default=None, description="Target asset symbol (e.g. CRO_USD)")
    base_commit: Optional[str] = Field(default=None, description="Requested base commit reference")
    resolved_commit_hash: Optional[str] = Field(default=None, description="Fully resolved VCS commit hash")
    commit_message: Optional[str] = Field(default=None, description="VCS commit message if resolved")
    commit_author: Optional[str] = Field(default=None, description="VCS commit author if resolved")
    proposed_commit: Optional[str] = Field(default=None, description="Target or proposed commit hash")
    approval_id: Optional[str] = Field(default=None, description="Identifier of the approval request")
    proposal_id: Optional[str] = Field(default=None, description="Identifier of the proposal")
    configuration_changes: list[ConfigChange] = Field(default_factory=list, description="Configuration changes from proposal")
    triggering_events: list[dict[str, Any]] = Field(default_factory=list, description="Relevant timeline/anomaly events")
    proposal_rationale: Optional[str] = Field(default=None, description="Overall proposal rationale")
    risks: list[str] = Field(default_factory=list, description="Identified risks")
    expected_effect: Optional[str] = Field(default=None, description="Expected operational effect")
    approval_status: Optional[str] = Field(default=None, description="Approval status (pending, approved, etc.)")
    consistency_warnings: list[str] = Field(default_factory=list, description="Inconsistencies detected against base commit state")
    evidence_limitations: list[str] = Field(default_factory=list, description="Gaps or missing evidence records")


class DecisionExplanation(BaseModel):
    summary: str = Field(description="High-level one sentence summary of the decision explanation")
    causal_story: str = Field(description="Full step-by-step causal chain narrative")
    key_factors: list[str] = Field(default_factory=list, description="Key factors leading to this decision")


class DecisionInvestigationPresentation(BaseModel):
    blocks: list[dict[str, Any]] = Field(default_factory=list, description="UI blocks for presentation")


class DecisionInvestigationResult(BaseModel):
    kind: Literal["decision_investigation"] = "decision_investigation"
    goal: Optional[AgentGoal] = None
    evidence: Optional[DecisionEvidence] = None
    explanation: Optional[DecisionExplanation] = None
    presentation: DecisionInvestigationPresentation
