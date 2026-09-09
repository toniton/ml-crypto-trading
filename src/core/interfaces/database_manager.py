from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.interfaces.unit_of_work import UnitOfWork


class DatabaseManager(ABC):
    """Abstract interface for database managers handling lifecycle and units of work."""

    @abstractmethod
    def initialize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_unit_of_work(self) -> UnitOfWork:
        raise NotImplementedError
