from datetime import datetime, timezone

from src.metrics.models.metric_query import MetricQuery
from src.metrics.models.metric_type import AggregationType, MetricType
from src.metrics.services.metric_service import MetricService


def _ts(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


class TestMetricService:
    def test_register_sets_default_aggregation(self, db_manager):
        service = MetricService(db_manager)

        counter = service.register("http.requests", metric_type=MetricType.COUNTER)
        gauge = service.register("queue.depth", metric_type=MetricType.GAUGE)
        histogram = service.register("http.duration", metric_type=MetricType.HISTOGRAM)

        assert counter.aggregation == AggregationType.SUM
        assert gauge.aggregation == AggregationType.LAST
        assert histogram.aggregation == AggregationType.AVG

    def test_increment_counter_sums_within_buckets(self, db_manager):
        service = MetricService(db_manager)
        service.increment("http.requests", value=1, timestamp=_ts(0))
        service.increment("http.requests", value=2, timestamp=_ts(0))
        service.increment("http.requests", value=3, timestamp=_ts(61))

        series = service.query(MetricQuery(metric_names=("http.requests",), interval_seconds=60))

        assert len(series) == 1
        assert [point.value for point in series[0].points] == [3.0, 3.0]

    def test_gauge_uses_last_aggregation(self, db_manager):
        service = MetricService(db_manager)
        service.gauge("portfolio.balance", value=100.0, timestamp=_ts(0))
        service.gauge("portfolio.balance", value=150.0, timestamp=_ts(10))

        series = service.query(MetricQuery(metric_names=("portfolio.balance",), interval_seconds=60))

        assert [point.value for point in series[0].points] == [150.0]

    def test_observe_uses_avg_aggregation(self, db_manager):
        service = MetricService(db_manager)
        service.observe("http.request.duration", value=10.0, timestamp=_ts(0))
        service.observe("http.request.duration", value=20.0, timestamp=_ts(0))

        series = service.query(MetricQuery(metric_names=("http.request.duration",), interval_seconds=60))

        assert [point.value for point in series[0].points] == [15.0]

    def test_query_filters_by_labels(self, db_manager):
        service = MetricService(db_manager)
        service.increment("http.requests", labels={"route": "/orders"}, timestamp=_ts(0))
        service.increment("http.requests", labels={"route": "/balance"}, timestamp=_ts(0))

        series = service.query(MetricQuery(
            metric_names=("http.requests",),
            interval_seconds=60,
            labels={"route": "/orders"},
        ))

        assert [point.value for point in series[0].points] == [1.0]

    def test_flush_persists_buffered_samples(self, db_manager):
        service = MetricService(db_manager)
        service.increment("http.requests", timestamp=_ts(0))
        assert service._buffer.__len__() == 1

        service.flush()

        assert service._buffer.__len__() == 0
        series = service.query(MetricQuery(metric_names=("http.requests",), interval_seconds=60))
        assert [point.value for point in series[0].points] == [1.0]

    def test_registered_names(self, db_manager):
        service = MetricService(db_manager)
        service.increment("http.requests")
        service.increment("http.errors")

        assert service.registered_names() == ["http.errors", "http.requests"]
