from __future__ import annotations

from typing import Optional

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent.evidence_proposal.nodes import (
    CollectAndEvaluateNode,
    PresentProposalNode,
    ResolveContextNode,
    SynthesizeNarrativeNode,
)
from src.agent.evidence_proposal.state import EvidenceProposalState
from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.llm_adapter import LlmAdapter
from src.vcs.application.service import VCSService


def _route_after_context(state: EvidenceProposalState) -> str:
    if state.get("resolution_status") == "NEEDS_CLARIFICATION":
        return "present_proposal"
    return "collect_and_evaluate"


def _route_after_collection(state: EvidenceProposalState) -> str:
    if state.get("resolution_status") == "EVIDENCE_UNAVAILABLE":
        return "present_proposal"
    return "synthesize_narrative"


class EvidenceProposalGraph:
    def __init__(
            self,
            llm: Optional[LlmAdapter] = None,
            db_manager: Optional[DatabaseManager] = None,
            vcs: Optional[VCSService] = None,
    ):
        self._llm = llm
        self._db_manager = db_manager
        self._vcs = vcs

    def build(self) -> CompiledStateGraph:
        builder = StateGraph(EvidenceProposalState)

        builder.add_node(
            "resolve_context",
            ResolveContextNode(db_manager=self._db_manager, vcs_service=self._vcs),
        )
        builder.add_node(
            "collect_and_evaluate",
            CollectAndEvaluateNode(db_manager=self._db_manager, vcs_service=self._vcs),
        )
        builder.add_node(
            "synthesize_narrative",
            SynthesizeNarrativeNode(llm=self._llm),
        )
        builder.add_node(
            "present_proposal",
            PresentProposalNode(db_manager=self._db_manager),
        )

        builder.add_edge(START, "resolve_context")
        builder.add_conditional_edges(
            "resolve_context",
            _route_after_context,
            {
                "present_proposal": "present_proposal",
                "collect_and_evaluate": "collect_and_evaluate",
            },
        )
        builder.add_conditional_edges(
            "collect_and_evaluate",
            _route_after_collection,
            {
                "present_proposal": "present_proposal",
                "synthesize_narrative": "synthesize_narrative",
            },
        )
        builder.add_edge("synthesize_narrative", "present_proposal")
        builder.add_edge("present_proposal", END)

        return builder.compile()
