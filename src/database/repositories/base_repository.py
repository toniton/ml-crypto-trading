import abc
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

T = TypeVar("T", bound=BaseModel)


class BaseRepository(Generic[T], metaclass=abc.ABCMeta):
    def __init__(self, database_session: Session):
        self.database_session = database_session

    @abc.abstractmethod
    def save(self, entity: T):
        raise NotImplementedError()

    @abc.abstractmethod
    def get(self, entity_id: str) -> Optional[T]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_all(self) -> List[T]:
        raise NotImplementedError()

    @abc.abstractmethod
    def update(self, entity_id: str, entity: T):
        raise NotImplementedError()

    @abc.abstractmethod
    def upsert(self, entity: T) -> None:
        raise NotImplementedError()
