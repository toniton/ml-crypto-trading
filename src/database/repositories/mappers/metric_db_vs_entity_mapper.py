from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from src.database.dao.metric_definition_dao import MetricDefinitionDao
from src.database.dao.metric_sample_dao import MetricSampleDao
from src.metrics.models.metric import MetricDefinition
from src.metrics.models.metric_sample import MetricSample
from src.metrics.models.metric_type import AggregationType, MetricType


def _to_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _to_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class MetricDefinitionDBVSEntityMapper:
    @staticmethod
    def map_to_db(entity: MetricDefinition) -> MetricDefinitionDao:
        return MetricDefinitionDao(
            id=entity.id,
            name=entity.name,
            metric_type=entity.metric_type.value,
            unit=entity.unit,
            description=entity.description,
            aggregation=entity.aggregation.value if entity.aggregation else None,
            retention_seconds=entity.retention_seconds,
            enabled=entity.enabled,
        )

    @staticmethod
    def map_to_entity(dao: MetricDefinitionDao) -> MetricDefinition:
        return MetricDefinition(
            name=dao.name,
            metric_type=MetricType(dao.metric_type),
            unit=dao.unit or "",
            description=dao.description or "",
            aggregation=AggregationType(dao.aggregation) if dao.aggregation else None,
            retention_seconds=dao.retention_seconds,
            enabled=dao.enabled,
            id=dao.id,
            created_at=_to_aware_utc(dao.created_at),
        )


class MetricSampleDBVSEntityMapper:
    @staticmethod
    def map_to_db(entity: MetricSample) -> MetricSampleDao:
        return MetricSampleDao(
            metric_id=entity.metric_id,
            timestamp=_to_naive_utc(entity.timestamp),
            value=entity.value,
            labels=dict(entity.labels),
        )

    @staticmethod
    def map_to_entity(dao: MetricSampleDao) -> MetricSample:
        return MetricSample(
            metric_id=cast(str, dao.metric_id),
            timestamp=_to_aware_utc(dao.timestamp),
            value=float(dao.value),
            labels=dict(dao.labels or {}),
        )
