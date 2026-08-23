from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class ProposalStore(ABC, Generic[T]):
    @abstractmethod
    def register(self, proposal_id: str, proposal: T) -> None:
        raise NotImplementedError()

    @abstractmethod
    def get(self, proposal_id: str) -> Optional[T]:
        raise NotImplementedError()

    @abstractmethod
    def remove(self, proposal_id: str) -> None:
        raise NotImplementedError()
