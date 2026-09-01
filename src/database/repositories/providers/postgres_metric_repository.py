from __future__ import annotations

from datetime import datetime
from typing import List, Optional, cast

from src.database.dao.metric_definition_dao import MetricDefinitionDao
from src.database.dao.metric_sample_dao import MetricSampleDao
from src.database.repositories.base_repository import T
from src.database.repositories.mappers.metric_db_vs_entity_mapper import (
    MetricDefinitionDBVSEntityMapper,
    MetricSampleDBVSEntityMapper,
)
from src.metrics.models.metric import MetricDefinition
from src.metrics.models.metric_sample import MetricSample
from src.metrics.storage.metric_repository import MetricRepository


class PostgresMetricRepository(MetricRepository):
    def save(self, entity: T):
        pass

    def get(self, entity_id: str) -> Optional[T]:
        pass

    def get_all(self) -> List[T]:
        pass

    def update(self, entity_id: str, entity: T):
        pass

    def upsert(self, entity: T) -> None:
        pass

    def save_definition(self, definition: MetricDefinition) -> None:
        self.database_session.add(MetricDefinitionDBVSEntityMapper.map_to_db(definition))

    def get_definition(self, name: str) -> MetricDefinition | None:
        definition = self.database_session.query(MetricDefinitionDao).filter(
            MetricDefinitionDao.name == name
        ).first()
        return MetricDefinitionDBVSEntityMapper.map_to_entity(definition) if definition else None

    def get_definitions(self) -> list[MetricDefinition]:
        definitions = self.database_session.query(MetricDefinitionDao).all()
        return [MetricDefinitionDBVSEntityMapper.map_to_entity(cast(MetricDefinitionDao, definition)) for definition in definitions]

    def save_samples(self, samples: list[MetricSample]) -> None:
        for sample in samples:
            self.database_session.add(MetricSampleDBVSEntityMapper.map_to_db(sample))

    def get_samples(self, metric_id: str, start: datetime, end: datetime) -> list[MetricSample]:
        samples = self.database_session.query(MetricSampleDao).filter(
            MetricSampleDao.metric_id == metric_id,
            MetricSampleDao.timestamp >= start,
            MetricSampleDao.timestamp <= end,
        ).all()
        return [MetricSampleDBVSEntityMapper.map_to_entity(cast(MetricSampleDao, sample)) for sample in samples]

    def delete_samples_before(self, metric_id: str, cutoff: datetime, batch_size: int) -> int:
        total = 0
        while True:
            ids = self.database_session.query(MetricSampleDao.id).filter(
                MetricSampleDao.metric_id == metric_id,
                MetricSampleDao.timestamp < cutoff,
            ).limit(batch_size).all()
            if not ids:
                break
            deleted = self.database_session.query(MetricSampleDao).filter(
                MetricSampleDao.id.in_([row[0] for row in ids])
            ).delete(synchronize_session=False)
            total += deleted
            if deleted < batch_size:
                break
        return total
