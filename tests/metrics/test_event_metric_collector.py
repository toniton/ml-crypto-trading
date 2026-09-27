from decimal import Decimal

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.events.message_event_bus import MessageEventBus
from src.metrics.collectors.event_metric_collector import EventMetricCollector
from src.metrics.models.constants import MetricLabelKey, MetricName
from src.metrics.models.metric_query import MetricQuery
from src.metrics.services.metric_service import MetricService
from src.trading.events import OrderFilledEvent, OrderSubmittedEvent


def _order() -> Order:
    return Order(
        uuid="o",
        provider_name="BACKTEST",
        ticker_symbol="BTC_USD",
        price=Decimal("100"),
        quantity="1",
        trade_action=TradeAction.BUY,
        created_time=0.0,
        commit_hash="56339b9",
    )


class TestEventMetricCollector:
    def test_increments_counter_on_event(self, db_manager):
        service = MetricService(db_manager)
        collector = EventMetricCollector(service)
        bus = MessageEventBus()
        collector.subscribe(bus)

        bus.publish(OrderSubmittedEvent(symbol="BTC_USD", order=_order()))
        bus.publish(OrderSubmittedEvent(symbol="BTC_USD", order=_order()))

        series = service.query(MetricQuery(
            metric_names=(MetricName.ORDERS_SUBMITTED_TOTAL.value,),
            interval_seconds=60,
        ))[0]
        assert [point.value for point in series.points] == [2.0]

    def test_increments_counter_with_labels_and_observes_latency(self, db_manager):
        service = MetricService(db_manager)
        collector = EventMetricCollector(service)
        bus = MessageEventBus()
        collector.subscribe(bus)

        order = _order()
        order.executed_time = 0.5  # 500ms latency
        bus.publish(OrderFilledEvent(symbol="BTC_USD", order=order))

        series = service.query(MetricQuery(
            metric_names=(MetricName.ORDERS_FILLED_TOTAL.value,),
            labels={
                MetricLabelKey.PROVIDER.value: "BACKTEST",
                MetricLabelKey.SYMBOL.value: "BTC_USD",
                MetricLabelKey.ACTION.value: "BUY",
            },
            interval_seconds=60,
        ))[0]
        assert [point.value for point in series.points] == [1.0]

        latency_series = service.query(MetricQuery(
            metric_names=(MetricName.ORDER_LATENCY_EXECUTION.value,),
            interval_seconds=60,
        ))[0]
        assert [point.value for point in latency_series.points] == [500.0]

    def test_custom_event_metric_mapping(self, db_manager):
        service = MetricService(db_manager)
        collector = EventMetricCollector(service, event_metric_map={"OrderSubmittedEvent": "custom.orders"})
        bus = MessageEventBus()
        collector.subscribe(bus)

        bus.publish(OrderSubmittedEvent(symbol="BTC_USD", order=_order()))

        series = service.query(MetricQuery(metric_names=("custom.orders",), interval_seconds=60))[0]
        assert [point.value for point in series.points] == [1.0]
