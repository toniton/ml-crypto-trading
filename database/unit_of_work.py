from typing import Type, TypeVar, cast
from sqlalchemy.orm import Session

from database.repositories.base_repository import BaseRepository
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin

T = TypeVar("T", bound=BaseRepository)


class UnitOfWork(ApplicationLoggingMixin):
    session: Session

    def __init__(self, session: Session):
        self.session = session

    def complete(self) -> None:
        try:
            if self.session.is_active:
                self.session.commit()
                self.app_logger.debug("Transaction committed")
            else:
                self.app_logger.warning("No active transaction to commit")
        except Exception as e:
            self.app_logger.error(f"Commit failed: {e}", exc_info=True)
            self.rollback()
            raise

    def rollback(self) -> None:
        try:
            if self.session.is_active:
                self.session.rollback()
                self.app_logger.debug("Transaction rolled back")
        except Exception as e:
            self.app_logger.error(f"Rollback failed: {e}", exc_info=True)

    def get_repository(self, repository_type: Type[T]) -> T:
        if issubclass(repository_type, BaseRepository):
            return cast(T, repository_type(database_session=self.session))
        raise ValueError(f'Repository for {repository_type} not found.')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_val:
                self.app_logger.error(f"Exception occurred: {exc_val}", exc_info=True)
                self.rollback()
            else:
                self.complete()
        finally:
            self.session.close()
            self.app_logger.debug("Session closed")
