from src.metrics.collectors.runtime_metrics_collector import (
    EventLoopLagMonitor,
    ProcessStatsTracker,
    RuntimeMetricsCollector,
)
from src.metrics.models.metric_query import MetricQuery
from src.metrics.services.metric_service import MetricService


class TestEventLoopLagMonitor:
    def test_record_lag_calculates_percentiles(self):
        monitor = EventLoopLagMonitor()
        lags = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 100.0]
        for lag in lags:
            monitor.record_lag(lag)

        stats = monitor.get_stats()
        assert stats["current_ms"] == 100.0
        assert stats["max_ms"] == 100.0
        assert stats["p50_ms"] >= 10.0
        assert stats["p95_ms"] >= 20.0
        assert stats["p99_ms"] >= 20.0

    def test_empty_lag_stats(self):
        monitor = EventLoopLagMonitor()
        stats = monitor.get_stats()
        assert stats["current_ms"] == 0.0
        assert stats["max_ms"] == 0.0
        assert stats["p50_ms"] == 0.0


class TestProcessStatsTracker:
    def test_process_stats_returns_valid_metrics(self):
        tracker = ProcessStatsTracker()
        rss_bytes = tracker.get_memory_rss_bytes()
        cpu_percent = tracker.get_cpu_percent()
        threads = tracker.get_threads_count()

        assert rss_bytes > 0
        assert isinstance(cpu_percent, float)
        assert cpu_percent >= 0.0
        assert threads >= 1


class TestRuntimeMetricsCollector:
    def test_registration_and_recording(self, db_manager):
        service = MetricService(db_manager)
        collector = RuntimeMetricsCollector(metric_service=service)

        collector.lag_monitor.record_lag(2.0)
        collector.lag_monitor.record_lag(8.0)
        collector.lag_monitor.record_lag(41.0)
        collector.lag_monitor.record_lag(812.0)

        snapshot = collector.collect_and_record()

        assert snapshot["status"] in ("healthy", "degraded", "unhealthy")
        assert snapshot["memory_rss_mb"] > 0
        assert snapshot["threads_count"] >= 1
        assert snapshot["event_loop_lag"]["max_ms"] == 812.0

        names = service.registered_names()
        assert "runtime.uptime" in names
        assert "runtime.memory" in names
        assert "runtime.cpu" in names
        assert "runtime.threads" in names
        assert "runtime.event_loop_lag" in names
        assert "runtime.last_heartbeat" in names

        series = service.query(MetricQuery(metric_names=("runtime.memory",), interval_seconds=60))
        assert len(series) == 1
        assert len(series[0].points) == 1

    def test_status_derivation(self, db_manager):
        service = MetricService(db_manager)
        collector = RuntimeMetricsCollector(metric_service=service)

        healthy_status = collector._derive_status({"p95_ms": 5.0, "max_ms": 20.0}, cpu_percent=10.0)
        assert healthy_status == "healthy"

        degraded_lag = collector._derive_status({"p95_ms": 60.0, "max_ms": 80.0}, cpu_percent=10.0)
        assert degraded_lag == "degraded"

        degraded_max = collector._derive_status({"p95_ms": 10.0, "max_ms": 600.0}, cpu_percent=10.0)
        assert degraded_max == "degraded"

        unhealthy_status = collector._derive_status({"p95_ms": 10.0, "max_ms": 6000.0}, cpu_percent=10.0)
        assert unhealthy_status == "unhealthy"

    def test_uptime_formatting(self, db_manager):
        service = MetricService(db_manager)
        collector = RuntimeMetricsCollector(metric_service=service)

        assert collector._format_uptime(45) == "45s"
        assert collector._format_uptime(125) == "2m 5s"
        assert collector._format_uptime(3665) == "1h 1m"
        assert collector._format_uptime(90000) == "1d 1h"
