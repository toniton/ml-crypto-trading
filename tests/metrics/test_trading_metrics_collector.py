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
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
    PositionChangedEvent,
    SignalGeneratedEvent,
    StrategyEvaluatedEvent,
    TradeClosedEvent,
)


def _order() -> Order:
    return Order(
        uuid="test-order-1",
        provider_name="BINANCE",
        ticker_symbol="BTC_USD",
        price=Decimal("50000"),
        quantity="1.0",
        trade_action=TradeAction.BUY,
        created_time=100.0,
        commit_hash="abc1234",
        winning_strategy="HammerStrategy",
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
        slippage=Decimal("5"),
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

        series = service.query(MetricQuery(
            metric_names=("evaluations.total",),
            labels={"symbol": "BTC_USD"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in series.points] == [1.0]

        sig_series = service.query(MetricQuery(
            metric_names=("signals.total",),
            labels={"symbol": "BTC_USD", "action": "BUY"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in sig_series.points] == [1.0]

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

        quorum_series = service.query(MetricQuery(
            metric_names=("consensus.quorum.total",),
            labels={"symbol": "BTC_USD", "action": "BUY", "quorum_met": "true"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in quorum_series.points] == [1.0]

    def test_tracks_rejections_and_risk_metrics(self, db_manager):
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
            reason=DecisionRejectedReason.RISK_REJECTED.value,
        ))

        snapshot = collector.get_funnel_snapshot("BTC_USD")
        assert snapshot["rejections"] == {
            DecisionRejectedReason.BELOW_MIN_QUANTITY.value: 1,
            DecisionRejectedReason.RISK_REJECTED.value: 1,
        }

        rej_series = service.query(MetricQuery(
            metric_names=("decisions.rejected.total",),
            labels={"symbol": "BTC_USD", "reason": DecisionRejectedReason.RISK_REJECTED.value},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in rej_series.points] == [1.0]

        risk_series = service.query(MetricQuery(
            metric_names=("risk.rejections.total",),
            labels={"symbol": "BTC_USD"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in risk_series.points] == [2.0]

    def test_tracks_order_lifecycle_metrics_with_labels(self, db_manager):
        service = MetricService(db_manager)
        collector = TradingMetricsCollector(service)
        bus = MessageEventBus()
        collector.subscribe(bus)

        order = _order()
        order.executed_time = 100.25  # 250ms execution latency

        bus.publish(OrderSubmittedEvent(symbol="BTC_USD", order=order))
        bus.publish(OrderFilledEvent(symbol="BTC_USD", order=order))
        bus.publish(OrderCancelledEvent(symbol="BTC_USD", order=order))
        bus.publish(OrderRejectedEvent(symbol="BTC_USD", order=order, reason="INSUFFICIENT_MARGIN"))

        snapshot = collector.get_funnel_snapshot("BTC_USD")
        assert snapshot["orders_submitted"] == 1
        assert snapshot["orders_filled"] == 1

        # Test canonical order metrics with labels
        sub_series = service.query(MetricQuery(
            metric_names=("orders.submitted.total",),
            labels={"symbol": "BTC_USD", "exchange": "BINANCE", "action": "BUY", "strategy": "HammerStrategy"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in sub_series.points] == [1.0]

        fill_series = service.query(MetricQuery(
            metric_names=("orders.filled.total",),
            labels={"symbol": "BTC_USD", "exchange": "BINANCE", "action": "BUY", "strategy": "HammerStrategy"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in fill_series.points] == [1.0]

        cancel_series = service.query(MetricQuery(
            metric_names=("orders.cancelled.total",),
            labels={"symbol": "BTC_USD"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in cancel_series.points] == [1.0]

        rej_series = service.query(MetricQuery(
            metric_names=("orders.rejected.total",),
            labels={"symbol": "BTC_USD", "reason": "INSUFFICIENT_MARGIN"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in rej_series.points] == [1.0]

    def test_records_closed_trade_financial_metrics(self, db_manager):
        service = MetricService(db_manager)
        collector = TradingMetricsCollector(service)
        bus = MessageEventBus()
        collector.subscribe(bus)

        trade = _closed_trade()
        bus.publish(TradeClosedEvent(symbol="BTC_USD", trade=trade))

        snapshot = collector.get_funnel_snapshot("BTC_USD")
        assert snapshot["trades_closed"] == 1

        # Check trades.closed.total
        closed_series = service.query(MetricQuery(
            metric_names=("trades.closed.total",),
            labels={"symbol": "BTC_USD", "strategy": "HammerStrategy", "commit_hash": "abc1234"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in closed_series.points] == [1.0]

        # Check pnl.realized.total (net_pnl = 2000 - 102 - 5 = 1893)
        pnl_series = service.query(MetricQuery(
            metric_names=("pnl.realized.total",),
            labels={"symbol": "BTC_USD", "strategy": "HammerStrategy"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in pnl_series.points] == [1893.0]

        # Check fees.paid.total (50 + 52 = 102)
        fees_series = service.query(MetricQuery(
            metric_names=("fees.paid.total",),
            labels={"symbol": "BTC_USD"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in fees_series.points] == [102.0]

        # Check slippage.cost.total
        slip_series = service.query(MetricQuery(
            metric_names=("slippage.cost.total",),
            labels={"symbol": "BTC_USD"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in slip_series.points] == [5.0]

    def test_records_position_changed_metrics(self, db_manager):
        service = MetricService(db_manager)
        collector = TradingMetricsCollector(service)
        bus = MessageEventBus()
        collector.subscribe(bus)

        bus.publish(PositionChangedEvent(
            symbol="BTC_USD",
            action="BUY",
            quantity=Decimal("1.0"),
            price=Decimal("50000"),
            position_qty=Decimal("1.0"),
            realized_pnl=Decimal("0"),
        ))

        series = service.query(MetricQuery(
            metric_names=("positions.changed.total",),
            labels={"symbol": "BTC_USD", "action": "BUY"},
            interval_seconds=60,
        ))[0]
        assert [point.value for point in series.points] == [1.0]

