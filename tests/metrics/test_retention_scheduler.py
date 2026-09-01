from datetime import datetime, timedelta, timezone

from src.metrics.services.metric_service import MetricService
from src.metrics.services.retention_engine import RetentionEngine
from src.metrics.services.retention_scheduler import RetentionScheduler


class TestRetentionScheduler:
    def test_run_once_deletes_expired_samples(self, db_manager):
        service = MetricService(db_manager)
        service.register("http.requests", retention_seconds=60)

        now = datetime.now(timezone.utc)
        service.increment("http.requests", timestamp=now - timedelta(seconds=120))
        service.flush()

        scheduler = RetentionScheduler(RetentionEngine(db_manager), cleanup_interval=timedelta(hours=1))
        result = scheduler.run_once()

        assert result.deleted_samples == 1

    def test_start_and_stop_lifecycle(self, db_manager):
        scheduler = RetentionScheduler(
            RetentionEngine(db_manager),
            cleanup_interval=timedelta(hours=1),
        )

        scheduler.start()
        scheduler.stop()

        assert scheduler._thread is not None
