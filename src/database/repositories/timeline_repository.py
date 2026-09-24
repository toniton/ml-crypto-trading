from __future__ import annotations

import abc
from typing import List, Optional

from src.database.repositories.base_repository import BaseRepository
from src.timeline.timeline_models import TimelineItem


class TimelineRepository(BaseRepository[TimelineItem], metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def save(self, entity: TimelineItem) -> TimelineItem:
        raise NotImplementedError()

    @abc.abstractmethod
    def save_batch(self, items: List[TimelineItem]) -> List[TimelineItem]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get(self, entity_id: str) -> Optional[TimelineItem]:
        raise NotImplementedError()

    @abc.abstractmethod
    def list_items(
            self,
            category: Optional[str] = None,
            severity: Optional[str] = None,
            correlation_id: Optional[str] = None,
            actor_type: Optional[str] = None,
            entity_type: Optional[str] = None,
            entity_id: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> List[TimelineItem]:
        raise NotImplementedError()
