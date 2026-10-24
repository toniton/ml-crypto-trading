from __future__ import annotations

from typing import Any, Optional, TypedDict

from api.interfaces.evidence_proposal import EvidenceBasedProposal
from src.agent.configuration.models import ConfigurationPresentation
from src.agent.router.models import AgentRoute
from src.proposals.models import CollectedEvidence


class EvidenceProposalState(TypedDict, total=False):
    user_prompt: str
    request: AgentRoute
    history: list[Any]
    operational_context: Any
    experiment_id: Optional[str]
    candidate_id: Optional[str]
    ticker_symbol: str
    baseline_commit: str
    candidate_commit: Optional[str]
    collected_evidence: CollectedEvidence
    evidence_proposal: EvidenceBasedProposal
    presentation: ConfigurationPresentation
