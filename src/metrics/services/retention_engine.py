from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.database.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_metric_repository import PostgresMetricRepository
from src.metrics.models.retention_policy import RetentionResult


class RetentionEngine:
    def __init__(
            self,
            db_manager: DatabaseManager,
            default_retention: timedelta = timedelta(days=30),
            batch_size: int = 10000,
    ):
        self._database_manager = db_manager
        self._default_retention = default_retention
        self._batch_size = batch_size

    def run(self, now: datetime | None = None) -> RetentionResult:
        started_at = now or datetime.now(timezone.utc)
        deleted = 0

        with self._database_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresMetricRepository)
            for definition in repository.get_definitions():
                if not definition.enabled:
                    continue
                retention = (
                    timedelta(seconds=definition.retention_seconds)
                    if definition.retention_seconds
                    else self._default_retention
                )
                cutoff = started_at - retention
                deleted += repository.delete_samples_before(
                    definition.id, cutoff, self._batch_size
                )

            completed_at = datetime.now(timezone.utc)
            return RetentionResult(
                deleted_samples=deleted,
                started_at=started_at,
                completed_at=completed_at,
            )
