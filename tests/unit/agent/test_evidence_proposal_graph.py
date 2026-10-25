from __future__ import annotations

from unittest.mock import MagicMock

from api.interfaces.evidence_proposal import (
    EvidenceStatus,
    ProposalRecommendation,
)
from src.agent.evidence_proposal.graph import EvidenceProposalGraph
from src.agent.evidence_proposal.models import NarrativeSynthesis
from src.agent.router.models import AgentIntent, AgentRoute
from src.agent.router.nodes.extract_references import extract_deterministic_references
from src.agent.router.nodes.understand_goal import UnderstandGoalNode


class TestEvidenceProposalGraph:
    def test_extract_references_parses_experiment_and_candidate_ids(self):
        refs = extract_deterministic_references(
            "Generate an evidence-based proposal for BTC_USD from exp_99a1b2 and cand_weights_1"
        )
        assert refs.asset == "BTC_USD"
        assert refs.experiment_id == "exp_99a1b2"
        assert refs.candidate_id == "cand_weights_1"

    def test_understand_goal_routes_evidence_proposal_requests(self):
        mock_llm = MagicMock()
        mock_llm.generate_structured.return_value = AgentRoute(intent=AgentIntent.GENERAL)
        node = UnderstandGoalNode(mock_llm)

        res = node(
            {
                "user_prompt": "Generate an evidence-based proposal for BTC_USD from exp_1234",
            }
        )
        route = res["route"]
        assert route.intent == AgentIntent.EVIDENCE_PROPOSAL
        assert route.references.experiment_id == "exp_1234"
        assert route.references.asset == "BTC_USD"

    def test_llm_writer_cannot_override_insufficient_verdict_or_metrics(self):
        mock_llm = MagicMock()
        mock_llm.generate_structured.return_value = NarrativeSynthesis(
            hypothesis="Adjusting BTC trading window may reduce low-liquidity exposure.",
            executive_summary="Pending out-of-sample validation before any live configuration change.",
        )

        graph = EvidenceProposalGraph(llm=mock_llm, db_manager=None, vcs=None).build()
        route = AgentRoute(intent=AgentIntent.EVIDENCE_PROPOSAL)

        state = graph.invoke(
            {
                "user_prompt": "Generate an evidence-based proposal for BTC_USD with cand_1",
                "request": route,
                "ticker_symbol": "BTC_USD",
                "candidate_id": "cand_1",
                "baseline_commit": "1111aaaa",
            }
        )

        proposal = state["evidence_proposal"]
        assert proposal.evidence_status == EvidenceStatus.INSUFFICIENT
        assert proposal.recommendation == ProposalRecommendation.INSUFFICIENT_EVIDENCE
        assert proposal.sample_size.candidate_trades == 0
        assert proposal.hypothesis == "Adjusting BTC trading window may reduce low-liquidity exposure."
        assert "Pending out-of-sample validation" in proposal.narrative_summary
        assert len(state["presentation"].blocks) == 1

    def test_resolve_context_missing_asset_prompts_clarification(self):
        graph = EvidenceProposalGraph(llm=None, db_manager=None, vcs=None).build()
        route = AgentRoute(intent=AgentIntent.EVIDENCE_PROPOSAL)

        state = graph.invoke(
            {
                "user_prompt": "Generate an evidence-based proposal",
                "request": route,
            }
        )

        assert state["resolution_status"] == "NEEDS_CLARIFICATION"
        assert state.get("evidence_proposal") is None
        assert "Clarification Needed" in state["presentation"].blocks[0].content

    def test_resolve_context_missing_experiment_prompts_clarification(self):
        graph = EvidenceProposalGraph(llm=None, db_manager=None, vcs=None).build()
        route = AgentRoute(intent=AgentIntent.EVIDENCE_PROPOSAL)

        state = graph.invoke(
            {
                "user_prompt": "Generate an evidence-based proposal for BTC_USD",
                "request": route,
                "ticker_symbol": "BTC_USD",
            }
        )

        assert state["resolution_status"] == "NEEDS_CLARIFICATION"
        assert state.get("evidence_proposal") is None
        assert "Clarification Needed" in state["presentation"].blocks[0].content

    def test_collect_and_evaluate_missing_db_reports_evidence_unavailable(self):
        graph = EvidenceProposalGraph(llm=None, db_manager=None, vcs=None).build()
        route = AgentRoute(intent=AgentIntent.EVIDENCE_PROPOSAL)

        state = graph.invoke(
            {
                "user_prompt": "Generate an evidence-based proposal for BTC_USD from exp_123",
                "request": route,
                "ticker_symbol": "BTC_USD",
                "experiment_id": "exp_123",
            }
        )

        assert state["resolution_status"] == "EVIDENCE_UNAVAILABLE"
        assert state.get("evidence_proposal") is None
        assert "Evidence Unavailable" in state["presentation"].blocks[0].content
