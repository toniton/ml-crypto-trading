from __future__ import annotations

from typing import List, Optional, cast

from api.interfaces.evidence_proposal import EvidenceBasedProposal
from src.database.dao.evidence_proposal_dao import EvidenceProposalDao
from src.database.repositories.evidence_proposal_repository import (
    EvidenceProposalRepository,
)


class PostgresEvidenceProposalRepository(EvidenceProposalRepository):

    def save(self, entity: EvidenceProposalDao) -> EvidenceProposalDao:
        existing = (
            self.database_session.query(EvidenceProposalDao)
            .filter(EvidenceProposalDao.id == entity.id)
            .first()
        )
        if existing:
            existing.experiment_id = entity.experiment_id
            existing.ticker_symbol = entity.ticker_symbol
            existing.baseline_commit = entity.baseline_commit
            existing.candidate_commit = entity.candidate_commit
            existing.candidate_id = entity.candidate_id
            existing.evidence_status = entity.evidence_status
            existing.recommendation = entity.recommendation
            existing.calculation_version = entity.calculation_version
            existing.payload = entity.payload
        else:
            self.database_session.add(entity)
        self.database_session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[EvidenceProposalDao]:
        row = (
            self.database_session.query(EvidenceProposalDao)
            .filter(EvidenceProposalDao.id == entity_id)
            .first()
        )
        return cast(Optional[EvidenceProposalDao], row)

    def get_all(self) -> List[EvidenceProposalDao]:
        rows = (
            self.database_session.query(EvidenceProposalDao)
            .order_by(EvidenceProposalDao.created_at.desc())
            .limit(100)
            .all()
        )
        return cast(List[EvidenceProposalDao], rows)

    def update(self, entity_id: str, entity: EvidenceProposalDao) -> None:
        self.save(entity)

    def upsert(self, entity: EvidenceProposalDao) -> None:
        self.save(entity)

    def save_proposal(self, proposal: EvidenceBasedProposal) -> EvidenceBasedProposal:
        payload = proposal.model_dump(mode="json")
        dao = EvidenceProposalDao(
            id=proposal.id,
            experiment_id=proposal.evidence_refs.experiment_id,
            ticker_symbol=proposal.ticker_symbol,
            baseline_commit=proposal.baseline_commit,
            candidate_commit=proposal.candidate_commit,
            candidate_id=proposal.candidate_id,
            evidence_status=proposal.evidence_status.value,
            recommendation=proposal.recommendation.value,
            calculation_version=proposal.calculation_version,
            payload=payload,
            created_at=proposal.created_at,
        )
        self.save(dao)
        return proposal

    def get_proposal(self, proposal_id: str) -> Optional[EvidenceBasedProposal]:
        row = self.get(proposal_id)
        if not row or not row.payload:
            return None
        return EvidenceBasedProposal.model_validate(row.payload)

    def list_proposals(
            self,
            experiment_id: Optional[str] = None,
            ticker_symbol: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[EvidenceBasedProposal]:
        query = self.database_session.query(EvidenceProposalDao)
        if experiment_id:
            query = query.filter(EvidenceProposalDao.experiment_id == experiment_id)
        if ticker_symbol:
            query = query.filter(EvidenceProposalDao.ticker_symbol == ticker_symbol)
        rows = (
            query.order_by(EvidenceProposalDao.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            EvidenceBasedProposal.model_validate(r.payload)
            for r in rows
            if r.payload
        ]
