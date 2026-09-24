from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.database.dao.timeline_item_dao import TimelineItemDao
from src.events.decision_models import ArtifactRef, EntityRef
from src.timeline.timeline_models import TimelineCategory, TimelineItem


def _parse_iso_to_datetime(iso_str: str) -> datetime:
    normalized = iso_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class TimelineDBVSEntityMapper:
    @staticmethod
    def map_to_db(entity: TimelineItem) -> TimelineItemDao:
        parsed_dt = _parse_iso_to_datetime(entity.timestamp)
        primary_entity_type = entity.primary_entity.type if entity.primary_entity else None
        primary_entity_id = entity.primary_entity.id if entity.primary_entity else None
        entities_data = [e.to_dict() for e in entity.entities] if entity.entities else None
        artifacts_data = [a.to_dict() for a in entity.artifacts] if entity.artifacts else None
        category_val = entity.category.value if isinstance(entity.category, TimelineCategory) else entity.category

        return TimelineItemDao(
            id=entity.timeline_id,
            timestamp=parsed_dt,
            category=category_val,
            severity=entity.severity,
            title=entity.title,
            summary=entity.summary,
            correlation_id=entity.correlation_id,
            causation_id=entity.causation_id,
            actor_type=entity.actor_type,
            actor_id=entity.actor_id,
            primary_entity_type=primary_entity_type,
            primary_entity_id=primary_entity_id,
            entities=entities_data,
            artifacts=artifacts_data,
            metadata_=entity.metadata or {},
        )

    @staticmethod
    def map_to_entity(dao: TimelineItemDao) -> TimelineItem:
        dt = _to_aware_utc(dao.timestamp)
        iso_timestamp = dt.isoformat() if dt else datetime.now(timezone.utc).isoformat()

        primary_entity = None
        if dao.primary_entity_type and dao.primary_entity_id:
            primary_entity = EntityRef(type=dao.primary_entity_type, id=dao.primary_entity_id)

        entities: list[EntityRef] = []
        if dao.entities and isinstance(dao.entities, list):
            entities = [
                EntityRef(type=item["type"], id=item["id"])
                for item in dao.entities
                if isinstance(item, dict) and "type" in item and "id" in item
            ]

        artifacts: list[ArtifactRef] = []
        if dao.artifacts and isinstance(dao.artifacts, list):
            artifacts = [
                ArtifactRef(type=item["type"], id=item["id"])
                for item in dao.artifacts
                if isinstance(item, dict) and "type" in item and "id" in item
            ]

        category_enum = TimelineCategory.SYSTEM
        if dao.category:
            try:
                category_enum = TimelineCategory(dao.category)
            except ValueError:
                category_enum = TimelineCategory.SYSTEM

        metadata_dict = dao.metadata_ if isinstance(dao.metadata_, dict) else {}

        return TimelineItem(
            timeline_id=dao.id,
            timestamp=iso_timestamp,
            category=category_enum,
            severity=dao.severity or "INFO",
            title=dao.title or "",
            summary=dao.summary or "",
            correlation_id=dao.correlation_id,
            causation_id=dao.causation_id,
            actor_type=dao.actor_type or "SYSTEM",
            actor_id=dao.actor_id,
            primary_entity=primary_entity,
            entities=entities,
            artifacts=artifacts,
            metadata=metadata_dict,
        )
