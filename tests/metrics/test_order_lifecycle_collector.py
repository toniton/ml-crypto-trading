import time
from decimal import Decimal

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.metrics.collectors.order_lifecycle_collector import OrderLifecycleCollector
from src.metrics.models.metric_query import MetricQuery
from src.metrics.services.metric_service import MetricService


def _create_order(uuid: str, status: OrderStatus, created_time: float) -> Order:
    return Order(
        uuid=uuid,
        provider_name="BINANCE",
        ticker_symbol="BTC_USD",
        price=Decimal("50000"),
        quantity="1.0",
        trade_action=TradeAction.BUY,
        created_time=created_time,
        commit_hash="56339b9",
        status=status,
    )


class TestOrderLifecycleCollector:
    def test_collects_gauges_and_detects_stuck_orders(self, db_manager: SqlAlchemyDatabaseManager):
        metric_service = MetricService(db_manager)
        collector = OrderLifecycleCollector(metric_service, db_manager)

        now = time.time()
        with db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresOrderRepository)
            repo.upsert(_create_order("o-1", OrderStatus.PENDING, now - 10))  # Healthy pending
            repo.upsert(_create_order("o-2", OrderStatus.PENDING, now - 40))  # Pending > 30s
            repo.upsert(_create_order("o-3", OrderStatus.PROCESSING, now - 400))  # Stuck > 5m
            repo.upsert(_create_order("o-4", OrderStatus.RECONCILIATION_REQUIRED, now - 20))

        snapshot = collector.collect_and_record()

        assert snapshot["status"] == "issues_detected"
        assert snapshot["consistency"]["pending"] == 2
        assert snapshot["consistency"]["processing"] == 1
        assert snapshot["consistency"]["reconciliation"] == 1
        assert snapshot["consistency"]["stuck_5m"] == 1
        assert snapshot["consistency"]["pending_gt_30s"] == 1

        series = metric_service.query(MetricQuery(metric_names=("orders.pending",), interval_seconds=60))[0]
        assert [point.value for point in series.points] == [2.0]

        stuck_series = metric_service.query(MetricQuery(metric_names=("orders.stuck_5m",), interval_seconds=60))[0]
        assert [point.value for point in stuck_series.points] == [1.0]
