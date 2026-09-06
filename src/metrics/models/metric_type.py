from enum import Enum


class MetricType(str, Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


class AggregationType(str, Enum):
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    LAST = "last"
    COUNT = "count"
    P50 = "p50"
    P90 = "p90"
    P95 = "p95"
    P99 = "p99"


def default_aggregation(metric_type: MetricType) -> AggregationType:
    if metric_type == MetricType.GAUGE:
        return AggregationType.LAST
    if metric_type == MetricType.HISTOGRAM:
        return AggregationType.AVG
    return AggregationType.SUM
