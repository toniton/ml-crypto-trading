from decimal import Decimal

from api.interfaces.order import Order
from api.interfaces.trade import Trade
from api.interfaces.trade_action import TradeAction
from src.events.message_event_bus import MessageEventBus
from src.metrics.collectors.trading_metrics_collector import TradingMetricsCollector
from src.metrics.models.metric_query import MetricQuery
from src.metrics.services.metric_service import MetricService
from src.trading.events import (
    ConsensusEvaluatedEvent,
    DecisionRejectedEvent,
    DecisionRejectedReason,
    OrderFilledEvent,
    OrderSubmittedEvent,
    SignalGeneratedEvent,
    StrategyEvaluatedEvent,
    TradeClosedEvent,
)


def _order() -> Order:
    return Order(
        uuid="test-order-1",
        provider_name="BACKTEST",
        ticker_symbol="BTC_USD",
        price=Decimal("50000"),
        quantity="1.0",
        trade_action=TradeAction.BUY,
        created_time=100.0,
        commit_hash="abc1234",
    )


def _closed_trade() -> Trade:
    return Trade.create(
        ticker_symbol="BTC_USD",
        entry_order_uuid="entry-1",
        exit_order_uuid="exit-1",
        entry_price=Decimal("50000"),
        exit_price=Decimal("52000"),
        quantity=Decimal("1.0"),
        entry_fee=Decimal("50"),
        exit_fee=Decimal("52"),
        entry_timestamp=100.0,
        exit_timestamp=200.0,
        commit_hash="abc1234",
        winning_strategy="HammerStrategy",
    )


class TestTradingMetricsCollector:
    def test_increments_evaluation_and_signal_metrics(self, db_manager):
        service = MetricService(db_manager)
        collector = TradingMetricsCollector(service)
        bus = MessageEventBus()
        collector.subscribe(bus)

        bus.publish(StrategyEvaluatedEvent(symbol="BTC_USD", evaluated_at=100.0))
        bus.publish(SignalGeneratedEvent(symbol="BTC_USD", action="BUY", generated_at=100.0))

        snapshot = collector.get_funnel_snapshot("BTC_USD")
        assert snapshot["evaluations"] == 1

    def test_tracks_consensus_passed_metrics(self, db_manager):
        service = MetricService(db_manager)
        collector = TradingMetricsCollector(service)
        bus = MessageEventBus()
        collector.subscribe(bus)

        bus.publish(ConsensusEvaluatedEvent(
            symbol="BTC_USD",
            decision="BUY",
            quorum_met=True,
            buy_votes=3,
            total_strategies=4,
        ))

        snapshot = collector.get_funnel_snapshot("BTC_USD")
        assert snapshot["consensus_passed"] == 1

    def test_tracks_rejections_grouped_by_reason(self, db_manager):
        service = MetricService(db_manager)
        collector = TradingMetricsCollector(service)
        bus = MessageEventBus()
        collector.subscribe(bus)

        bus.publish(DecisionRejectedEvent(
            symbol="BTC_USD",
            action="BUY",
            reason=DecisionRejectedReason.BELOW_MIN_QUANTITY.value,
        ))
        bus.publish(DecisionRejectedEvent(
            symbol="BTC_USD",
            action="BUY",
            reason=DecisionRejectedReason.NEGATIVE_EDGE.value,
        ))

        snapshot = collector.get_funnel_snapshot("BTC_USD")
        assert snapshot["rejections"] == {
            DecisionRejectedReason.BELOW_MIN_QUANTITY.value: 1,
            DecisionRejectedReason.NEGATIVE_EDGE.value: 1,
        }

    def test_tracks_orders_and_fills_in_funnel(self, db_manager):
        service = MetricService(db_manager)
        collector = TradingMetricsCollector(service)
        bus = MessageEventBus()
        collector.subscribe(bus)

        order = _order()
        bus.publish(OrderSubmittedEvent(symbol="BTC_USD", order=order))
        bus.publish(OrderFilledEvent(symbol="BTC_USD", order=order))

        snapshot = collector.get_funnel_snapshot("BTC_USD")
        assert snapshot["orders_submitted"] == 1

    def test_records_closed_trade_metrics(self, db_manager):
        service = MetricService(db_manager)
        collector = TradingMetricsCollector(service)
        bus = MessageEventBus()
        collector.subscribe(bus)

        trade = _closed_trade()
        bus.publish(TradeClosedEvent(symbol="BTC_USD", trade=trade))

        snapshot = collector.get_funnel_snapshot("BTC_USD")
        assert snapshot["trades_closed"] == 1

    def test_funnel_conversion_rates_calculation(self, db_manager):
        service = MetricService(db_manager)
        collector = TradingMetricsCollector(service)
        bus = MessageEventBus()
        collector.subscribe(bus)

        bus.publish(StrategyEvaluatedEvent(symbol="BTC_USD", evaluated_at=100.0))
        bus.publish(StrategyEvaluatedEvent(symbol="BTC_USD", evaluated_at=101.0))
        bus.publish(SignalGeneratedEvent(symbol="BTC_USD", action="BUY", generated_at=100.0))
        bus.publish(OrderSubmittedEvent(symbol="BTC_USD", order=_order()))
        bus.publish(OrderFilledEvent(symbol="BTC_USD", order=_order()))

        snapshot = collector.get_funnel_snapshot("BTC_USD")
        assert snapshot["conversion_rates"]["eval_to_signal_pct"] == 50.0

    def test_query_metric_service_counters(self, db_manager):
        service = MetricService(db_manager)
        collector = TradingMetricsCollector(service)
        bus = MessageEventBus()
        collector.subscribe(bus)

        bus.publish(StrategyEvaluatedEvent(symbol="BTC_USD", evaluated_at=100.0))

        series = service.query(MetricQuery(
            metric_names=("trading.evaluations.total",),
            labels={"symbol": "BTC_USD"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in series.points] == [1.0]
