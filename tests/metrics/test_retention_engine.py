from datetime import datetime, timedelta, timezone

from src.metrics.services.metric_service import MetricService
from src.metrics.services.retention_engine import RetentionEngine


class TestRetentionEngine:
    def test_deletes_samples_older_than_retention(self, db_manager):
        service = MetricService(db_manager)
        service.register("http.requests", retention_seconds=60)

        now = datetime.now(timezone.utc)
        service.increment("http.requests", timestamp=now - timedelta(seconds=120))
        service.increment("http.requests", timestamp=now - timedelta(seconds=10))
        service.flush()

        result = RetentionEngine(db_manager).run(now=now)

        assert result.deleted_samples == 1
