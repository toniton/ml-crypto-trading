from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.metrics.models.metric_query import MetricQuery
from src.metrics.models.metric_type import AggregationType
from src.metrics.services.metric_service import MetricService


class MetricsQueryInput(BaseModel):
    metric_names: Optional[list[str]] = Field(
        default=None,
        description=(
            "Names of metrics to query (e.g. ['orders.submitted', 'orders.executed', 'http.requests']). "
            "If omitted or empty, returns all registered metric names."
        ),
    )
    lookback_seconds: int = Field(
        default=3600,
        description="History window in seconds to query backwards from now (default: 3600 = 1 hour).",
    )
    interval_seconds: int = Field(
        default=60,
        description="Bucket aggregation interval in seconds (default: 60 = 1 minute).",
    )
    aggregation: Optional[str] = Field(
        default=None,
        description="Aggregation function ('sum', 'avg', 'min', 'max', 'last', 'count').",
    )
    labels: Optional[dict[str, str]] = Field(
        default=None,
        description="Optional key-value labels to filter metric samples.",
    )


class MetricsTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "query_metrics"
    description: str = (
        "Query historical time-series metrics (e.g. order submission/execution counts, "
        "HTTP request latency/errors) or discover registered metrics for performance and system analysis."
    )
    args_schema: Type[BaseModel] = MetricsQueryInput
    metric_service: MetricService

    def __init__(self, metric_service: MetricService):
        super().__init__(metric_service=metric_service)

    def _run(  # pylint: disable=arguments-differ
            self,
            metric_names: Optional[list[str]] = None,
            lookback_seconds: int = 3600,
            interval_seconds: int = 60,
            aggregation: Optional[str] = None,
            labels: Optional[dict[str, str]] = None,
    ) -> str:
        if not metric_names:
            registered = self.metric_service.registered_names()
            self.app_logger.info("Registered metric names requested by LLM.")
            return f"Available registered metrics: {', '.join(registered) if registered else 'None'}"

        now = datetime.now(timezone.utc)
        start = now - timedelta(seconds=max(lookback_seconds, 1))
        query = MetricQuery(
            metric_names=tuple(metric_names),
            start_time=start,
            end_time=now,
            interval_seconds=max(interval_seconds, 1),
            aggregation=self._resolve_aggregation(aggregation),
            labels=labels or {},
        )

        try:
            series = self.metric_service.query(query)
            self.app_logger.info(f"Metrics query executed for {metric_names}.")
            if not series:
                return f"No metric data found for: {', '.join(metric_names)}"
            return "\n".join(self._format_series(s) for s in series)
        except Exception as exc:  # pylint: disable=broad-except
            err = f"Failed to query metrics: {exc}"
            self.app_logger.error(err)
            return err

    @staticmethod
    def _resolve_aggregation(aggregation: Optional[str]) -> Optional[AggregationType]:
        if not aggregation:
            return None
        try:
            return AggregationType(aggregation.lower())
        except ValueError:
            return None

    @staticmethod
    def _format_series(series) -> str:
        points_str = ", ".join(
            f"{p.timestamp.strftime('%H:%M:%S')}: {p.value:.4f}"
            for p in series.points
        )
        values = [p.value for p in series.points]
        summary = (
            f"count={len(values)}, sum={sum(values):.4f}, "
            f"avg={sum(values) / len(values):.4f}" if values else "count=0"
        )
        return (
            f"Metric: {series.name} (unit: '{series.unit}', interval: {series.interval_seconds}s, {summary}):\n"
            f"  Points: [{points_str}]"
        )
