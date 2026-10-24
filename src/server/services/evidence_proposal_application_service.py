from __future__ import annotations

import uuid
from typing import Any, Optional

from api.interfaces.evidence_proposal import (
    EvidenceBasedProposal,
    EvidenceStatus,
    GenerateCommitProposalRequest,
    GenerateExperimentProposalRequest,
    ProposalRecommendation,
)
from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.proposal_store import ProposalStore
from src.database.repositories.providers.postgres_evidence_proposal_repository import (
    PostgresEvidenceProposalRepository,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.proposals.evidence_collector import EvidenceCollector
from src.proposals.proposal_validator import ProposalValidator
from src.vcs.application.service import VCSService
from src.vcs.domain.diff import ConfigurationProposal


class EvidenceProposalApplicationService(ApplicationLoggingMixin):
    def __init__(
            self,
            db_manager: DatabaseManager,
            vcs_service: Optional[VCSService] = None,
            proposal_store: Optional[ProposalStore[ConfigurationProposal]] = None,
    ):
        self._db_manager = db_manager
        self._vcs_service = vcs_service
        self._proposal_store = proposal_store
        self._collector = EvidenceCollector(db_manager=db_manager, vcs_service=vcs_service)

    def generate_from_experiment(
            self,
            experiment_id: str,
            req: GenerateExperimentProposalRequest,
    ) -> EvidenceBasedProposal:
        evidence = self._collector.collect_from_experiment(
            experiment_id=experiment_id,
            candidate_id=req.candidate_id,
            hypothesis=req.hypothesis,
            title=req.title,
            triggered_by=req.triggered_by,
        )
        proposal = ProposalValidator.build_and_validate_proposal(evidence)
        return self.save_proposal(proposal)

    def generate_from_commits(
            self,
            req: GenerateCommitProposalRequest,
    ) -> EvidenceBasedProposal:
        evidence = self._collector.collect_from_commits(req)
        proposal = ProposalValidator.build_and_validate_proposal(evidence)
        return self.save_proposal(proposal)

    def save_proposal(self, proposal: EvidenceBasedProposal) -> EvidenceBasedProposal:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresEvidenceProposalRepository)
            return repo.save_proposal(proposal)

    def get_proposal(self, proposal_id: str) -> Optional[EvidenceBasedProposal]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresEvidenceProposalRepository)
            return repo.get_proposal(proposal_id)

    def list_proposals(
            self,
            experiment_id: Optional[str] = None,
            ticker_symbol: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[EvidenceBasedProposal]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresEvidenceProposalRepository)
            return repo.list_proposals(
                experiment_id=experiment_id,
                ticker_symbol=ticker_symbol,
                limit=limit,
                offset=offset,
            )

    def prepare_configuration_approval(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Evidence proposal '{proposal_id}' not found.")

        if proposal.evidence_status in (EvidenceStatus.INSUFFICIENT, EvidenceStatus.INCOMPARABLE):
            raise ValueError(
                f"Cannot prepare configuration approval for proposal '{proposal_id}' "
                f"with evidence status '{proposal.evidence_status.value}'."
            )

        if proposal.recommendation not in (
            ProposalRecommendation.PROMOTE_TO_APPROVAL,
            ProposalRecommendation.ACCEPT_FOR_TESTING,
        ):
            raise ValueError(
                f"Cannot prepare configuration approval when recommendation is "
                f"'{proposal.recommendation.value}'."
            )

        if not proposal.candidate_commit:
            raise ValueError(
                f"Proposal '{proposal_id}' has no candidate commit to prepare for approval."
            )

        changes = []
        if self._vcs_service:
            changes = self._vcs_service.diff(proposal.baseline_commit, proposal.candidate_commit)

        config_proposal = ConfigurationProposal(
            summary=proposal.title,
            changes=changes,
            risks=list(proposal.limitations),
            expected_effect=proposal.proposed_changes_summary,
            base_commit_hash=proposal.baseline_commit,
        )

        approval_proposal_id = f"cfg_{proposal.id}_{uuid.uuid4().hex[:6]}"
        if self._proposal_store is not None:
            self._proposal_store.register(approval_proposal_id, config_proposal)

        return {
            "evidence_proposal_id": proposal.id,
            "configuration_proposal_id": approval_proposal_id,
            "requires_human_approval": True,
            "configuration_proposal": config_proposal.model_dump(mode="json"),
        }
