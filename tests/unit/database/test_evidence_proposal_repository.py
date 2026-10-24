from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.interfaces.evidence_proposal import (
    EvidenceBasedProposal,
    EvidenceReference,
    EvidenceStatus,
    ProposalRecommendation,
)
from src.database.dao.evidence_proposal_dao import EvidenceProposalDao
from src.database.repositories.providers.postgres_evidence_proposal_repository import (
    PostgresEvidenceProposalRepository,
)
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class TestEvidenceProposalRepository:  # pylint: disable=attribute-defined-outside-init
    def setup_method(self):
        self.engine = create_engine("sqlite:///:memory:")
        SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(
            self.engine, tables=[EvidenceProposalDao.__table__]
        )
        session_factory = sessionmaker(bind=self.engine)
        self.session = session_factory()
        self.repo = PostgresEvidenceProposalRepository(database_session=self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_save_and_get_proposal_round_trip(self):
        proposal = EvidenceBasedProposal(
            id="ebp_001",
            title="BTC Strategy Window Proposal",
            ticker_symbol="BTC_USD",
            hypothesis="Restricting trading hours reduces drawdown.",
            baseline_commit="base_111",
            candidate_commit="cand_222",
            candidate_id="cand_1",
            evidence_refs=EvidenceReference(experiment_id="exp_100"),
            evidence_status=EvidenceStatus.SUFFICIENT,
            recommendation=ProposalRecommendation.PROMOTE_TO_APPROVAL,
        )

        self.repo.save_proposal(proposal)
        self.session.commit()

        loaded = self.repo.get_proposal("ebp_001")
        assert loaded is not None
        assert loaded.id == "ebp_001"
        assert loaded.ticker_symbol == "BTC_USD"
        assert loaded.evidence_status == EvidenceStatus.SUFFICIENT
        assert loaded.recommendation == ProposalRecommendation.PROMOTE_TO_APPROVAL
        assert loaded.evidence_refs.experiment_id == "exp_100"

    def test_list_proposals_filters_by_experiment_and_ticker(self):
        p1 = EvidenceBasedProposal(
            id="ebp_a",
            title="BTC Proposal",
            ticker_symbol="BTC_USD",
            hypothesis="H1",
            baseline_commit="b1",
            evidence_refs=EvidenceReference(experiment_id="exp_1"),
        )
        p2 = EvidenceBasedProposal(
            id="ebp_b",
            title="ETH Proposal",
            ticker_symbol="ETH_USD",
            hypothesis="H2",
            baseline_commit="b2",
            evidence_refs=EvidenceReference(experiment_id="exp_2"),
        )
        self.repo.save_proposal(p1)
        self.repo.save_proposal(p2)
        self.session.commit()

        by_exp = self.repo.list_proposals(experiment_id="exp_1")
        assert len(by_exp) == 1
        assert by_exp[0].id == "ebp_a"

        by_ticker = self.repo.list_proposals(ticker_symbol="ETH_USD")
        assert len(by_ticker) == 1
        assert by_ticker[0].id == "ebp_b"

    def test_table_columns_exist(self):
        inspector = sa.inspect(self.engine)
        cols = {c["name"] for c in inspector.get_columns("evidence_proposals")}
        assert {
            "id",
            "experiment_id",
            "ticker_symbol",
            "baseline_commit",
            "candidate_commit",
            "candidate_id",
            "evidence_status",
            "recommendation",
            "calculation_version",
            "payload",
            "created_at",
        }.issubset(cols)
