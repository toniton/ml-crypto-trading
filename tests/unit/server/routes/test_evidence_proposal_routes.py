from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.interfaces.evidence_proposal import (
    EvidenceBasedProposal,
    EvidenceReference,
    EvidenceStatus,
    ProposalRecommendation,
)
from src.server.routes.evidence_proposal_routes import create_evidence_proposal_router
from src.server.routes.experiment_routes import create_experiment_router
from src.server.services.evidence_proposal_application_service import (
    EvidenceProposalApplicationService,
)
from src.vcs.domain.diff import ConfigChange


class TestEvidenceProposalRoutes:  # pylint: disable=attribute-defined-outside-init
    def setup_method(self):
        self.app = FastAPI()
        self.mock_service = MagicMock()
        self.app.state.evidence_proposal_service = self.mock_service
        self.app.state.experiment_service = MagicMock()
        self.app.include_router(create_evidence_proposal_router())
        self.app.include_router(create_experiment_router())
        self.client = TestClient(self.app)

    def test_generate_experiment_proposal_endpoint(self):
        proposal = EvidenceBasedProposal(
            id="ebp_exp_1",
            title="BTC Proposal",
            ticker_symbol="BTC_USD",
            hypothesis="Adjust weights",
            baseline_commit="base_1",
            candidate_commit="cand_1_hash",
            candidate_id="cand_1",
            evidence_refs=EvidenceReference(experiment_id="exp_10"),
        )
        self.mock_service.generate_from_experiment.return_value = proposal

        res = self.client.post(
            "/api/v1/experiments/exp_10/proposals",
            json={"candidate_id": "cand_1", "hypothesis": "Adjust weights"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["id"] == "ebp_exp_1"
        assert data["evidence_status"] == "INSUFFICIENT"

    def test_get_evidence_proposal_not_found(self):
        self.mock_service.get_proposal.return_value = None

        res = self.client.get("/api/v1/proposals/evidence/non_existent")
        assert res.status_code == 404

    def test_prepare_approval_rejects_insufficient_evidence(self):
        mock_db = MagicMock()
        mock_uow = MagicMock()
        mock_db.get_unit_of_work.return_value.__enter__.return_value = mock_uow
        mock_repo = MagicMock()
        mock_uow.get_repository.return_value = mock_repo

        insufficient_proposal = EvidenceBasedProposal(
            id="ebp_insuff",
            title="Insufficient Proposal",
            ticker_symbol="BTC_USD",
            hypothesis="Test",
            baseline_commit="base_1",
            candidate_commit="cand_1",
            evidence_status=EvidenceStatus.INSUFFICIENT,
            recommendation=ProposalRecommendation.INSUFFICIENT_EVIDENCE,
        )
        mock_repo.get_proposal.return_value = insufficient_proposal

        srv = EvidenceProposalApplicationService(db_manager=mock_db)
        self.app.state.evidence_proposal_service = srv

        res = self.client.post("/api/v1/proposals/evidence/ebp_insuff/prepare-approval")
        assert res.status_code == 400
        assert "INSUFFICIENT" in res.json()["detail"]

    def test_prepare_approval_registers_configuration_proposal_when_sufficient(self):
        mock_db = MagicMock()
        mock_uow = MagicMock()
        mock_db.get_unit_of_work.return_value.__enter__.return_value = mock_uow
        mock_repo = MagicMock()
        mock_uow.get_repository.return_value = mock_repo

        mock_vcs = MagicMock()
        mock_vcs.diff.return_value = [
            ConfigChange(
                path="assets.BTC_USD.strategies.RsiBuy.weight",
                old_value=1.0,
                new_value=1.5,
                reason="Walk-forward validated improvement",
            )
        ]
        mock_store = MagicMock()

        sufficient_proposal = EvidenceBasedProposal(
            id="ebp_ok",
            title="Validated BTC Weight Adjustment",
            ticker_symbol="BTC_USD",
            hypothesis="Test",
            baseline_commit="base_1",
            candidate_commit="cand_1",
            evidence_status=EvidenceStatus.SUFFICIENT,
            recommendation=ProposalRecommendation.PROMOTE_TO_APPROVAL,
        )
        mock_repo.get_proposal.return_value = sufficient_proposal

        srv = EvidenceProposalApplicationService(
            db_manager=mock_db,
            vcs_service=mock_vcs,
            proposal_store=mock_store,
        )
        self.app.state.evidence_proposal_service = srv

        res = self.client.post("/api/v1/proposals/evidence/ebp_ok/prepare-approval")
        assert res.status_code == 200
        body = res.json()
        assert body["evidence_proposal_id"] == "ebp_ok"
        assert body["requires_human_approval"] is True
        mock_store.register.assert_called_once()
