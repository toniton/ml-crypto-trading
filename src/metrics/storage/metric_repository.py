from __future__ import annotations

from abc import abstractmethod
from datetime import datetime

from src.database.repositories.base_repository import BaseRepository
from src.metrics.models.metric import MetricDefinition
from src.metrics.models.metric_sample import MetricSample


class MetricRepository(BaseRepository[MetricDefinition]):
    @abstractmethod
    def save_definition(self, definition: MetricDefinition) -> None:
        raise NotImplementedError()

    @abstractmethod
    def get_definition(self, name: str) -> MetricDefinition | None:
        raise NotImplementedError()

    @abstractmethod
    def get_definitions(self) -> list[MetricDefinition]:
        raise NotImplementedError()

    @abstractmethod
    def save_samples(self, samples: list[MetricSample]) -> None:
        raise NotImplementedError()

    @abstractmethod
    def get_samples(self, metric_id: str, start: datetime, end: datetime) -> list[MetricSample]:
        raise NotImplementedError()

    @abstractmethod
    def delete_samples_before(self, metric_id: str, cutoff: datetime, batch_size: int) -> int:
        raise NotImplementedError()
