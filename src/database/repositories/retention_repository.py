from __future__ import annotations

import abc
from typing import List, Optional

from src.database.repositories.base_repository import BaseRepository
from src.retention.models import DataCategory, RetentionAuditEvent, RetentionRun


class RetentionRepository(BaseRepository, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def save_run(self, run: RetentionRun) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def update_run(self, run: RetentionRun) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_run(self, run_id: str) -> Optional[RetentionRun]:
        raise NotImplementedError()

    @abc.abstractmethod
    def list_runs(self, limit: int = 20) -> List[RetentionRun]:
        raise NotImplementedError()

    @abc.abstractmethod
    def add_audit_event(self, event: RetentionAuditEvent) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def list_audit_events(self, limit: int = 100) -> List[RetentionAuditEvent]:
        raise NotImplementedError()

    @abc.abstractmethod
    def is_category_held(self, category: DataCategory) -> bool:
        raise NotImplementedError()

    @abc.abstractmethod
    def add_hold(self, category: DataCategory, reason: str, entity_id: Optional[str] = None) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def release_hold(self, hold_id: str) -> bool:
        raise NotImplementedError()
