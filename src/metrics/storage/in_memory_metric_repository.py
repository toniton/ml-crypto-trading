from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from src.database.repositories.base_repository import T
from src.metrics.models.metric import MetricDefinition
from src.metrics.models.metric_sample import MetricSample
from src.metrics.storage.metric_repository import MetricRepository


class InMemoryMetricRepository(MetricRepository):
    """In-memory implementation, useful for tests and lightweight deployments."""

    def __init__(self) -> None:
        self._definitions: dict[str, MetricDefinition] = {}
        self._samples_by_metric: dict[str, list[MetricSample]] = {}

    def save(self, entity: T) -> None:
        pass

    def get(self, entity_id: str) -> Optional[T]:
        return None

    def get_all(self) -> List[T]:
        return []

    def update(self, entity_id: str, entity: T) -> None:
        pass

    def upsert(self, entity: T) -> None:
        pass

    def save_definition(self, definition: MetricDefinition) -> None:
        self._definitions[definition.name] = definition

    def get_definition(self, name: str) -> MetricDefinition | None:
        return self._definitions.get(name)

    def get_definitions(self) -> list[MetricDefinition]:
        return list(self._definitions.values())

    def save_samples(self, samples: list[MetricSample]) -> None:
        for sample in samples:
            self._samples_by_metric.setdefault(sample.metric_id, []).append(sample)

    def get_samples(self, metric_id: str, start: datetime, end: datetime) -> list[MetricSample]:
        samples = self._samples_by_metric.get(metric_id, [])
        return [s for s in samples if start <= s.timestamp <= end]

    def delete_samples_before(self, metric_id: str, cutoff: datetime, batch_size: int) -> int:
        samples = self._samples_by_metric.get(metric_id, [])
        retained = [s for s in samples if s.timestamp >= cutoff]
        deleted = len(samples) - len(retained)
        self._samples_by_metric[metric_id] = retained
        return deleted
