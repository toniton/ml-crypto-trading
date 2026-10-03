from __future__ import annotations

from typing import Optional

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent.actions.service import AgentApprovalService
from src.agent.decision_investigation.nodes.build_evidence import BuildEvidenceNode
from src.agent.decision_investigation.nodes.explain_decision import ExplainDecisionNode
from src.agent.decision_investigation.nodes.load_timeline import LoadTimelineNode
from src.agent.decision_investigation.nodes.present_explanation import PresentExplanationNode
from src.agent.decision_investigation.nodes.resolve_commit import ResolveCommitNode
from src.agent.decision_investigation.nodes.resolve_proposal import ResolveProposalNode
from src.agent.decision_investigation.state import DecisionInvestigationState
from src.core.interfaces.llm_adapter import LlmAdapter
from src.server.timeline_projector import TimelineProjector
from src.vcs.application.service import VCSService


class DecisionInvestigationGraph:
    def __init__(
            self,
            llm: LlmAdapter,
            approval_service: Optional[AgentApprovalService] = None,
            vcs: Optional[VCSService] = None,
            timeline_projector: Optional[TimelineProjector] = None,
    ):
        self._llm = llm
        self._approval_service = approval_service
        self._vcs = vcs
        self._timeline_projector = timeline_projector

    def build(self) -> CompiledStateGraph:
        builder = StateGraph(DecisionInvestigationState)

        builder.add_node("resolve_proposal", ResolveProposalNode(self._approval_service, self._timeline_projector))
        builder.add_node("resolve_commit", ResolveCommitNode(self._vcs))
        builder.add_node("load_timeline", LoadTimelineNode(self._timeline_projector))
        builder.add_node("build_evidence", BuildEvidenceNode())
        builder.add_node("explain_decision", ExplainDecisionNode(self._llm))
        builder.add_node("present_explanation", PresentExplanationNode())

        builder.add_edge(START, "resolve_proposal")
        builder.add_edge("resolve_proposal", "resolve_commit")
        builder.add_edge("resolve_commit", "load_timeline")
        builder.add_edge("load_timeline", "build_evidence")
        builder.add_edge("build_evidence", "explain_decision")
        builder.add_edge("explain_decision", "present_explanation")
        builder.add_edge("present_explanation", END)

        return builder.compile()
