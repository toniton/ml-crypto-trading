from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.agent.configuration.models import MarkdownBlock


class MetricQueryIntent(BaseModel):
    metric_names: list[str] = Field(
        default_factory=list,
        description="Names of metrics to fetch (e.g. ['orders.submitted']). Empty to discover available metrics.",
    )

    lookback_seconds: int = Field(
        default=3600,
        description="Lookback window in seconds (default: 3600 = 1 hour).",
    )
    interval_seconds: int = Field(
        default=60,
        description="Bucket aggregation interval in seconds (default: 60 = 1 minute).",
    )
    aggregation: Optional[str] = Field(
        default=None,
        description="Aggregation function ('sum', 'avg', 'min', 'max', 'last', 'count').",
    )
    labels: dict[str, str] = Field(
        default_factory=dict,
        description="Key-value label filters.",
    )
    analysis_focus: str = Field(
        default="performance",
        description="Specific analytical question or focus (e.g. throughput, latency, errors, trade volume).",
    )


class AnalyticsPresentation(BaseModel):
    blocks: list[MarkdownBlock] = Field(default_factory=list)
