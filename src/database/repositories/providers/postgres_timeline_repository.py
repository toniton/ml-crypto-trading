from __future__ import annotations

from typing import List, Optional

from src.database.dao.timeline_item_dao import TimelineItemDao
from src.database.repositories.mappers.timeline_db_vs_entity_mapper import TimelineDBVSEntityMapper
from src.database.repositories.timeline_repository import TimelineRepository
from src.timeline.timeline_models import TimelineItem


class PostgresTimelineRepository(TimelineRepository):
    def save(self, entity: TimelineItem) -> TimelineItem:
        dao = TimelineDBVSEntityMapper.map_to_db(entity)
        merged_dao = self.database_session.merge(dao)
        self.database_session.flush()
        return TimelineDBVSEntityMapper.map_to_entity(merged_dao)

    def save_batch(self, items: List[TimelineItem]) -> List[TimelineItem]:
        if not items:
            return []
        saved_entities: List[TimelineItem] = []
        for item in items:
            dao = TimelineDBVSEntityMapper.map_to_db(item)
            merged_dao = self.database_session.merge(dao)
            saved_entities.append(TimelineDBVSEntityMapper.map_to_entity(merged_dao))
        self.database_session.flush()
        return saved_entities

    def get(self, entity_id: str) -> Optional[TimelineItem]:
        dao = (
            self.database_session.query(TimelineItemDao)
            .filter(TimelineItemDao.id == entity_id)
            .first()
        )
        if not dao:
            return None
        return TimelineDBVSEntityMapper.map_to_entity(dao)

    def get_all(self) -> List[TimelineItem]:
        return self.list_items(limit=1000)

    def update(self, entity_id: str, entity: TimelineItem):
        return self.save(entity)

    def upsert(self, entity: TimelineItem) -> None:
        self.save(entity)

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
        query = self.database_session.query(TimelineItemDao)
        if category:
            query = query.filter(TimelineItemDao.category == category)
        if severity:
            query = query.filter(TimelineItemDao.severity == severity)
        if correlation_id:
            query = query.filter(TimelineItemDao.correlation_id == correlation_id)
        if actor_type:
            query = query.filter(TimelineItemDao.actor_type == actor_type)
        if entity_type and entity_id:
            query = query.filter(
                (TimelineItemDao.primary_entity_type == entity_type)
                & (TimelineItemDao.primary_entity_id == entity_id)
            )
        elif entity_type:
            query = query.filter(TimelineItemDao.primary_entity_type == entity_type)
        elif entity_id:
            query = query.filter(TimelineItemDao.primary_entity_id == entity_id)

        daos = (
            query.order_by(TimelineItemDao.timestamp.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [TimelineDBVSEntityMapper.map_to_entity(dao) for dao in daos]
