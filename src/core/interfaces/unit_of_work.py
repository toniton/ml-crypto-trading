from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Type, TypeVar

T = TypeVar("T")


class UnitOfWork(ABC):
    @abstractmethod
    def complete(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_repository(self, repository_type: Type[T]) -> T:
        raise NotImplementedError

    @abstractmethod
    def __enter__(self) -> UnitOfWork:
        raise NotImplementedError

    @abstractmethod
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        raise NotImplementedError
