from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from api.interfaces.evidence_proposal import EvidenceBasedProposal
from src.agent.configuration.models import ConfigurationPresentation
from src.agent.router.models import AgentGoal


class NarrativeSynthesis(BaseModel):
    hypothesis: str = Field(
        default="",
        description="Refined statement of what change is proposed and why it might work.",
    )
    executive_summary: str = Field(
        default="",
        description="Concise explanation of the deterministic findings, trade-offs, and recommendation.",
    )


class EvidenceProposalResult(BaseModel):
    kind: Literal["evidence_proposal"] = "evidence_proposal"
    goal: Optional[AgentGoal] = None
    evidence_proposal: Optional[EvidenceBasedProposal] = None
    presentation: ConfigurationPresentation = Field(
        default_factory=ConfigurationPresentation.empty
    )
    resolution_status: Optional[str] = None
    status_message: Optional[str] = None
