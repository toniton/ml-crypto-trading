from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Dict, List

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.metrics.models.metric_type import AggregationType, MetricType
from src.metrics.models.metric_query import MetricQuery
from src.metrics.services.metric_service import MetricService


class OrderLifecycleCollector:
    STUCK_THRESHOLD_SECONDS = 300.0  # 5 minutes
    PENDING_ALERT_THRESHOLD_SECONDS = 30.0

    def __init__(
            self,
            metric_service: MetricService,
            database_manager: DatabaseManager,
    ):
        self._metric_service = metric_service
        self._database_manager = database_manager
        self._register_definitions()

    def _register_definitions(self) -> None:
        self._metric_service.register(
            "orders.pending",
            metric_type=MetricType.GAUGE,
            unit="orders",
            description="Current pending orders count",
            aggregation=AggregationType.LAST,
        )
        self._metric_service.register(
            "orders.processing",
            metric_type=MetricType.GAUGE,
            unit="orders",
            description="Current processing orders count",
            aggregation=AggregationType.LAST,
        )
        self._metric_service.register(
            "orders.reconciliation_required",
            metric_type=MetricType.GAUGE,
            unit="orders",
            description="Current reconciliation required orders count",
            aggregation=AggregationType.LAST,
        )
        self._metric_service.register(
            "orders.unknown",
            metric_type=MetricType.GAUGE,
            unit="orders",
            description="Current unknown status orders count",
            aggregation=AggregationType.LAST,
        )
        self._metric_service.register(
            "orders.state_mismatch",
            metric_type=MetricType.GAUGE,
            unit="orders",
            description="Orders with persistence state mismatches",
            aggregation=AggregationType.LAST,
        )
        self._metric_service.register(
            "orders.stuck_5m",
            metric_type=MetricType.GAUGE,
            unit="orders",
            description="Orders open and stuck for more than 5 minutes",
            aggregation=AggregationType.LAST,
        )
        self._metric_service.register(
            "orders.pending_gt_30s",
            metric_type=MetricType.GAUGE,
            unit="orders",
            description="Orders pending for more than 30 seconds",
            aggregation=AggregationType.LAST,
        )
        self._metric_service.register(
            "orders.orphaned",
            metric_type=MetricType.GAUGE,
            unit="orders",
            description="Orphaned orders without exchange match",
            aggregation=AggregationType.LAST,
        )

    def collect_and_record(self) -> Dict[str, Any]:
        snapshot = self.get_snapshot()
        now = datetime.now(timezone.utc)

        consistency = snapshot["consistency"]
        self._metric_service.gauge("orders.pending", consistency["pending"], timestamp=now)
        self._metric_service.gauge("orders.processing", consistency["processing"], timestamp=now)
        self._metric_service.gauge("orders.reconciliation_required", consistency["reconciliation"], timestamp=now)
        self._metric_service.gauge("orders.unknown", consistency["unknown"], timestamp=now)
        self._metric_service.gauge("orders.state_mismatch", consistency["state_mismatches"], timestamp=now)
        self._metric_service.gauge("orders.stuck_5m", consistency["stuck_5m"], timestamp=now)
        self._metric_service.gauge("orders.pending_gt_30s", consistency["pending_gt_30s"], timestamp=now)
        self._metric_service.gauge("orders.orphaned", consistency["orphaned"], timestamp=now)
        self._metric_service.flush()

        return snapshot

    def get_snapshot(self) -> Dict[str, Any]:
        non_terminal_orders = self._fetch_non_terminal_orders()
        now_ts = time.time()

        pending_count = 0
        processing_count = 0
        reconciliation_count = 0
        unknown_count = 0
        stuck_5m_count = 0
        pending_gt_30s_count = 0
        orphaned_count = 0
        state_mismatch_count = 0

        for order in non_terminal_orders:
            status = order.status
            if status == OrderStatus.PENDING:
                pending_count += 1
                if (now_ts - order.created_time) > self.PENDING_ALERT_THRESHOLD_SECONDS:
                    pending_gt_30s_count += 1
            elif status == OrderStatus.PROCESSING:
                processing_count += 1
            elif status == OrderStatus.RECONCILIATION_REQUIRED:
                reconciliation_count += 1
            elif status == OrderStatus.UNKNOWN or status is None:
                unknown_count += 1

            if (now_ts - order.created_time) > self.STUCK_THRESHOLD_SECONDS:
                stuck_5m_count += 1

        recent_latencies = self._calculate_stage_latencies()
        funnel_counts = self._calculate_funnel_counts(pending_count, processing_count, reconciliation_count, unknown_count)

        status_text = "healthy"
        if stuck_5m_count > 0 or reconciliation_count > 0 or state_mismatch_count > 0:
            status_text = "issues_detected"
        elif pending_gt_30s_count > 0 or unknown_count > 0:
            status_text = "degraded"

        return {
            "status": status_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "funnel": funnel_counts,
            "consistency": {
                "healthy": max(0, len(non_terminal_orders) - stuck_5m_count - reconciliation_count - unknown_count),
                "pending": pending_count,
                "processing": processing_count,
                "reconciliation": reconciliation_count,
                "unknown": unknown_count,
                "state_mismatches": state_mismatch_count,
                "stuck_5m": stuck_5m_count,
                "pending_gt_30s": pending_gt_30s_count,
                "orphaned": orphaned_count,
            },
            "latencies": {
                **recent_latencies,
                "pending_gt_30s": pending_gt_30s_count,
                "pending_gt_5m": stuck_5m_count,
            },
        }

    def _fetch_non_terminal_orders(self) -> List[Order]:
        try:
            with self._database_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresOrderRepository)
                return repo.get_non_terminal()
        except Exception:
            return []

    def _calculate_funnel_counts(
            self, pending: int, processing: int, reconciliation: int, unknown: int
    ) -> Dict[str, int]:
        submitted = self._query_metric_sum("orders.submitted")
        executed = self._query_metric_sum("orders.executed")
        cancelled = self._query_metric_sum("orders.cancelled")
        rejected = self._query_metric_sum("orders.rejected")

        return {
            "submitted": int(submitted),
            "executed": int(executed),
            "cancelled": int(cancelled),
            "rejected": int(rejected),
            "pending": pending,
            "processing": processing,
            "reconciliation_required": reconciliation,
            "unknown": unknown,
        }

    def _calculate_stage_latencies(self) -> Dict[str, float]:
        submit_p95 = self._query_metric_value("order.latency.submit", AggregationType.P95)
        execution_p95 = self._query_metric_value("order.latency.execution", AggregationType.P95)
        terminal_p95 = self._query_metric_value("order.latency.terminal", AggregationType.P95)

        return {
            "submit_ms_p95": round(submit_p95, 2),
            "execution_ms_p95": round(execution_p95, 2),
            "completion_ms_p95": round(terminal_p95, 2),
        }

    def _query_metric_sum(self, name: str) -> float:
        try:
            series = self._metric_service.query(MetricQuery(
                metric_names=(name,),
                aggregation=AggregationType.SUM,
                interval_seconds=86400 * 30,
            ))
            if series and series[0].points:
                return sum(p.value for p in series[0].points)
        except Exception:
            pass
        return 0.0

    def _query_metric_value(self, name: str, aggregation: AggregationType) -> float:
        try:
            series = self._metric_service.query(MetricQuery(
                metric_names=(name,),
                aggregation=aggregation,
                interval_seconds=86400 * 30,
            ))
            if series and series[0].points:
                return float(series[0].points[-1].value)
        except Exception:
            pass
        return 0.0
