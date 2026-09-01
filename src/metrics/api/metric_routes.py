from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

from src.metrics.models.metric_query import MetricQuery
from src.metrics.models.metric_series import MetricSeries
from src.metrics.models.metric_type import AggregationType
from src.metrics.services.metric_service import MetricService


def _series_to_json(series: MetricSeries) -> dict:
    return {
        "metric": series.name,
        "unit": series.unit,
        "interval": series.interval_seconds,
        "start": series.start_time.isoformat(),
        "end": series.end_time.isoformat(),
        "series": [
            {"timestamp": point.timestamp.isoformat(), "value": point.value}
            for point in series.points
        ],
    }


def _parse_aggregation(value: Optional[str]) -> Optional[AggregationType]:
    if not value:
        return None
    try:
        return AggregationType(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown aggregation: {value}") from exc


def create_metric_router(metric_service: MetricService) -> APIRouter:
    router = APIRouter()

    @router.get("/metrics")
    def list_metrics():
        return {"metrics": sorted(metric_service.registered_names())}

    @router.get("/metrics/{metric_name}")
    def get_metric(
            metric_name: str,
            start: Optional[datetime] = None,
            end: Optional[datetime] = None,
            interval: int = 60,
            aggregation: Optional[str] = None,
    ):
        query = MetricQuery(
            metric_names=(metric_name,),
            start_time=start,
            end_time=end,
            interval_seconds=interval,
            aggregation=_parse_aggregation(aggregation),
        )
        series = metric_service.query(query)
        if not series:
            raise HTTPException(status_code=404, detail=f"Unknown metric: {metric_name}")
        return _series_to_json(series[0])

    return router
