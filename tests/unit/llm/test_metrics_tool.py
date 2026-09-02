from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.llm.tools.metrics_tool import MetricsTool
from src.metrics.models.metric_series import MetricPoint, MetricSeries
from src.metrics.services.metric_service import MetricService


class TestMetricsTool:
    def test_empty_metric_names_returns_registered_list(self):
        service = MagicMock(spec=MetricService)
        service.registered_names.return_value = ["http.requests", "orders.submitted"]
        tool = MetricsTool(metric_service=service)


        result = tool.invoke({"metric_names": []})

        assert "http.requests" in result
        assert "orders.submitted" in result
        service.registered_names.assert_called_once()
        service.query.assert_not_called()

    def test_query_formats_series_data_and_summary(self):
        service = MagicMock(spec=MetricService)
        now = datetime.now(timezone.utc)
        series = MetricSeries(
            name="orders.submitted",
            unit="count",
            interval_seconds=60,
            start_time=now,
            end_time=now,
            points=(
                MetricPoint(timestamp=now, value=3.0),
                MetricPoint(timestamp=now, value=5.0),
            ),
        )
        service.query.return_value = [series]
        tool = MetricsTool(metric_service=service)

        result = tool.invoke({
            "metric_names": ["orders.submitted"],
            "lookback_seconds": 300,
            "interval_seconds": 60,
            "aggregation": "sum",
            "labels": {"asset": "BTC_USD"},
        })

        assert "Metric: orders.submitted" in result
        assert "sum=8.0000" in result
        assert "avg=4.0000" in result
        assert "count=2" in result
        service.query.assert_called_once()

    def test_query_no_data_returns_not_found(self):
        service = MagicMock(spec=MetricService)
        service.query.return_value = []
        tool = MetricsTool(metric_service=service)

        result = tool.invoke({"metric_names": ["unknown.metric"]})

        assert "No metric data found for: unknown.metric" in result

    def test_query_handles_service_exception(self):
        service = MagicMock(spec=MetricService)
        service.query.side_effect = RuntimeError("database connection failed")
        tool = MetricsTool(metric_service=service)

        result = tool.invoke({"metric_names": ["orders.submitted"]})


        assert "Failed to query metrics" in result
        assert "database connection failed" in result
