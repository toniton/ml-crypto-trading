from __future__ import annotations

from typing import Any, List, Optional, Type, TypeVar, cast

from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.unit_of_work import UnitOfWork

T = TypeVar("T")


class NoopRepository:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def save(self, entity: Any) -> Any:
        return entity

    def get(self, entity_id: Any) -> Optional[Any]:
        return None

    def get_all(self) -> List[Any]:
        return []

    def update(self, entity_id: Any, entity: Any) -> None:
        pass

    def upsert(self, entity: Any) -> None:
        pass

    def get_non_terminal(self) -> List[Any]:
        return []

    def get_by_date_range(self, *args: Any, **kwargs: Any) -> List[Any]:
        return []

    def get_by_status(self, *args: Any, **kwargs: Any) -> List[Any]:
        return []

    def __getattr__(self, name: str) -> Any:
        def _noop(*args: Any, **kwargs: Any) -> Any:
            return None

        return _noop


class NoopUnitOfWork(UnitOfWork):
    def __init__(self) -> None:
        self._repo = NoopRepository()

    def complete(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def get_repository(self, repository_type: Type[T]) -> T:
        return cast(T, self._repo)

    def __enter__(self) -> NoopUnitOfWork:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class NoopDatabaseManager(DatabaseManager):
    def initialize(self) -> None:
        pass

    def get_unit_of_work(self) -> UnitOfWork:
        return NoopUnitOfWork()
