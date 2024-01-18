import abc

from pydantic import BaseModel
from sqlalchemy.orm import Session


class BaseRepository(metaclass=abc.ABCMeta):
    def __init__(self, database_session: Session):
        self.database_session = database_session

    @abc.abstractmethod
    def save(self, entity: BaseModel):
        raise NotImplementedError()

    @abc.abstractmethod
    def get(self, entity_id: str):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_all(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def update(self, entity_id: str, entity: BaseModel):
        raise NotImplementedError()
