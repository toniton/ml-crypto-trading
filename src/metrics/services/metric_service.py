from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.database.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_metric_repository import PostgresMetricRepository
from src.metrics.models.metric import MetricDefinition
from src.metrics.models.metric_query import MetricQuery
from src.metrics.models.metric_sample import MetricSample
from src.metrics.models.metric_series import MetricPoint, MetricSeries
from src.metrics.models.metric_type import AggregationType, MetricType, default_aggregation
from src.metrics.storage.metric_buffer import MetricBuffer


class MetricService:
    def __init__(
            self,
            db_manager: DatabaseManager,
            buffer: Optional[MetricBuffer] = None,
    ):
        self._database_manager = db_manager
        self._buffer = buffer or MetricBuffer()
        self._definitions: dict[str, MetricDefinition] = {}

    def register(
            self,
            name: str,
            metric_type: MetricType = MetricType.COUNTER,
            unit: str = "",
            description: str = "",
            aggregation: Optional[AggregationType] = None,
            retention_seconds: int = 30 * 24 * 3600,
    ) -> MetricDefinition:
        definition = MetricDefinition(
            name=name,
            metric_type=metric_type,
            unit=unit,
            description=description,
            aggregation=aggregation or default_aggregation(metric_type),
            retention_seconds=retention_seconds,
        )
        with self._database_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresMetricRepository)
            repository.save_definition(definition)
            self._definitions[name] = definition
            return definition

    def increment(
            self,
            name: str,
            value: float = 1.0,
            labels: Optional[dict[str, str]] = None,
            timestamp: Optional[datetime] = None,
    ) -> None:
        self._record(name, value, labels, timestamp, MetricType.COUNTER)

    def gauge(
            self,
            name: str,
            value: float,
            labels: Optional[dict[str, str]] = None,
            timestamp: Optional[datetime] = None,
    ) -> None:
        self._record(name, value, labels, timestamp, MetricType.GAUGE)

    def observe(
            self,
            name: str,
            value: float,
            labels: Optional[dict[str, str]] = None,
            timestamp: Optional[datetime] = None,
    ) -> None:
        self._record(name, value, labels, timestamp, MetricType.HISTOGRAM)

    def flush(self) -> None:
        samples = self._buffer.drain()
        if samples:
            with self._database_manager.get_unit_of_work() as uow:
                repository = uow.get_repository(PostgresMetricRepository)
                repository.save_samples(samples)

    def registered_names(self) -> list[str]:
        with self._database_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresMetricRepository)
            definitions = repository.get_definitions()
        return sorted(definition.name for definition in definitions)

    def query(self, query: MetricQuery) -> list[MetricSeries]:
        self.flush()

        now = datetime.now(timezone.utc)
        start = query.start_time or datetime.fromtimestamp(0, tz=timezone.utc)
        end = query.end_time or now

        series: list[MetricSeries] = []
        for name in query.metric_names:
            definition = self._resolve_definition(name)
            if definition is None or not definition.enabled:
                continue

            with self._database_manager.get_unit_of_work() as uow:
                repository = uow.get_repository(PostgresMetricRepository)
                samples = repository.get_samples(definition.id, start, end)

            samples = [s for s in samples if self._matches_labels(s.labels, query.labels)]
            aggregation = (
                    query.aggregation
                    or definition.aggregation
                    or default_aggregation(definition.metric_type)
            )
            points = self._aggregate(samples, query.interval_seconds, aggregation)

            series.append(MetricSeries(
                name=name,
                unit=definition.unit,
                interval_seconds=query.interval_seconds,
                start_time=start,
                end_time=end,
                points=points,
            ))
        return series

    def _record(
            self,
            name: str,
            value: float,
            labels: Optional[dict[str, str]],
            timestamp: Optional[datetime],
            metric_type: MetricType,
    ) -> None:
        definition = self._ensure_definition(name, metric_type)
        if not definition.enabled:
            return
        self._buffer.append(MetricSample(
            metric_id=definition.id,
            timestamp=timestamp or datetime.now(timezone.utc),
            value=float(value),
            labels=dict(labels or {}),
        ))

    def _ensure_definition(self, name: str, metric_type: MetricType) -> MetricDefinition:
        definition = self._definitions.get(name)
        if definition is None:
            with self._database_manager.get_unit_of_work() as uow:
                repository = uow.get_repository(PostgresMetricRepository)
                definition = repository.get_definition(name)
            if definition is None:
                definition = self.register(name, metric_type=metric_type)
            else:
                self._definitions[name] = definition
        return definition

    def _resolve_definition(self, name: str) -> Optional[MetricDefinition]:
        definition = self._definitions.get(name)
        if definition is None:
            with self._database_manager.get_unit_of_work() as uow:
                repository = uow.get_repository(PostgresMetricRepository)
                definition = repository.get_definition(name)
            if definition is not None:
                self._definitions[name] = definition
        return definition

    @staticmethod
    def _matches_labels(sample_labels: dict[str, str], query_labels: dict[str, str]) -> bool:
        return all(sample_labels.get(key) == value for key, value in query_labels.items())

    @staticmethod
    def _aggregate(
            samples: list[MetricSample],
            interval_seconds: int,
            aggregation: AggregationType,
    ) -> tuple[MetricPoint, ...]:
        if not samples:
            return ()

        buckets: dict[datetime, list[float]] = {}
        for sample in samples:
            bucket = MetricService._bucket_start(sample.timestamp, interval_seconds)
            buckets.setdefault(bucket, []).append(sample.value)

        points = [
            MetricPoint(timestamp=bucket, value=MetricService._aggregate_values(values, aggregation))
            for bucket, values in sorted(buckets.items())
        ]
        return tuple(points)

    @staticmethod
    def _bucket_start(timestamp: datetime, interval_seconds: int) -> datetime:
        interval_seconds = max(interval_seconds, 1)
        epoch = int(timestamp.timestamp())
        bucket = epoch - (epoch % interval_seconds)
        return datetime.fromtimestamp(bucket, tz=timezone.utc)

    @staticmethod
    def _aggregate_values(values: list[float], aggregation: AggregationType) -> float:
        if aggregation == AggregationType.SUM:
            return sum(values)
        if aggregation == AggregationType.AVG:
            return sum(values) / len(values)
        if aggregation == AggregationType.MIN:
            return min(values)
        if aggregation == AggregationType.MAX:
            return max(values)
        if aggregation == AggregationType.LAST:
            return values[-1]
        if aggregation == AggregationType.COUNT:
            return float(len(values))
        raise ValueError(f"Unsupported aggregation: {aggregation}")
