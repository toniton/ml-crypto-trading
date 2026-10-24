from __future__ import annotations

import abc
from typing import Optional

from api.interfaces.evidence_proposal import EvidenceBasedProposal
from src.database.dao.evidence_proposal_dao import EvidenceProposalDao
from src.database.repositories.base_repository import BaseRepository


class EvidenceProposalRepository(BaseRepository[EvidenceProposalDao]):

    @abc.abstractmethod
    def save_proposal(self, proposal: EvidenceBasedProposal) -> EvidenceBasedProposal:
        raise NotImplementedError

    @abc.abstractmethod
    def get_proposal(self, proposal_id: str) -> Optional[EvidenceBasedProposal]:
        raise NotImplementedError

    @abc.abstractmethod
    def list_proposals(
            self,
            experiment_id: Optional[str] = None,
            ticker_symbol: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[EvidenceBasedProposal]:
        raise NotImplementedError
