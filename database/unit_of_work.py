from typing import Generic, TypeVar, cast
from sqlalchemy.orm import Session

from database.repositories.base_repository import BaseRepository

T = TypeVar("T", bound=BaseRepository)


class UnitOfWork:
    session: Session

    def __init__(self, session: Session):
        self.session = session

    def complete(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()

    def get_repository(self, repository_type: Generic[T]) -> T:
        if issubclass(repository_type, BaseRepository):
            return cast(T, repository_type(database_session=self.session))
        else:
            raise ValueError(f'Repository for {repository_type} not found.')

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            self.session.rollback()
        else:
            self.session.commit()
        self.session.close()
