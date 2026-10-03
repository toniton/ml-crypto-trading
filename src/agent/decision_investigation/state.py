from __future__ import annotations

from typing import Any, Optional, TypedDict

from src.agent.actions.models import AgentApprovalRequest
from src.agent.decision_investigation.models import (
    DecisionEvidence,
    DecisionExplanation,
    DecisionInvestigationPresentation,
)
from src.agent.router.models import AgentReferences, AgentRoute
from src.core.interfaces.llm_adapter import ChatTurn
from src.vcs.domain.diff import ConfigChange


class DecisionInvestigationState(TypedDict, total=False):
    user_prompt: str
    request: Optional[AgentRoute]
    history: list[ChatTurn]
    references: Optional[AgentReferences]
    approval: Optional[AgentApprovalRequest]
    resolved_commit_hash: Optional[str]
    commit_message: Optional[str]
    commit_author: Optional[str]
    base_config: Optional[dict[str, Any]]
    commit_diff_changes: list[ConfigChange]
    timeline_items: list[dict[str, Any]]
    evidence: Optional[DecisionEvidence]
    explanation: Optional[DecisionExplanation]
    presentation: Optional[DecisionInvestigationPresentation]
