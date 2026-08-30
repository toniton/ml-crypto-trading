from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.agent.oracle.events import (
    ORACLE_SUMMARY_EVENT_TYPE,
    OracleSummaryEvent,
)
from src.agent.oracle.oracle_adapter import OracleEventAdapter
from src.agent.oracle.oracle_context import MAX_OBSERVATIONS, OracleContext
from src.agent.oracle.oracle_service import OracleService
from src.agent.oracle.oracle_tool import AnalyzeTradingStateTool, GetTradingSummaryTool
from src.backtest.domain.result import PortfolioSnapshot
from src.backtest.events.domain_events import (
    OrderFilledEvent,
    OrderSubmittedEvent,
    PortfolioSnapshotEvent,
)
from src.core.interfaces.event import Event
from src.events.message_event_bus import CallbackSubscription, MessageEventBus
from src.trading.events import MarketStateChanged, OrderSubmitted, PositionChanged


def _make_order(symbol: str = "BTC_USD", action: TradeAction = TradeAction.BUY) -> Order:
    return Order(
        uuid="order-1",
        provider_name="BACKTEST",
        ticker_symbol=symbol,
        price=Decimal("100"),
        quantity="1.5",
        trade_action=action,
        created_time=1_700_000_000.0,
    )


class TestOracleContext:
    def test_is_due_initial_and_interval(self):
        context = OracleContext(summary_interval=timedelta(minutes=5))
        t0 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        assert context.is_due(t0) is True
        context.mark_summarized(t0)
        assert context.is_due(t0 + timedelta(minutes=4)) is False
        assert context.is_due(t0 + timedelta(minutes=5)) is True

    def test_symbol_created_on_demand(self):
        context = OracleContext()
        assert "BTC_USD" not in context.symbols
        context.symbol("BTC_USD").current_price = Decimal("1")
        assert context.symbol("BTC_USD").current_price == Decimal("1")

    def test_order_history_is_bounded(self):
        context = OracleContext()
        for _ in range(MAX_OBSERVATIONS + 10):
            OracleEventAdapter().apply(
                OrderSubmitted(symbol="BTC_USD", order=_make_order()),
                context,
            )
        assert len(context.symbol("BTC_USD").recent_orders) == MAX_OBSERVATIONS


class TestOracleEventAdapter:
    def test_market_state_live(self):
        context = OracleContext()
        OracleEventAdapter().apply(
            MarketStateChanged(symbol="BTC_USD", price=Decimal("101.5"), market_timestamp=1_700_000_000.0),
            context,
        )
        assert context.symbol("BTC_USD").current_price == Decimal("101.5")

    def test_order_submitted_backtest(self):
        context = OracleContext()
        OracleEventAdapter().apply(OrderSubmittedEvent(order=_make_order()), context)
        orders = context.symbol("BTC_USD").recent_orders
        assert len(orders) == 1
        assert orders[0].order_id == "order-1"
        assert orders[0].action == "BUY"
        assert orders[0].quantity == Decimal("1.5")

    def test_order_submitted_live(self):
        context = OracleContext()
        OracleEventAdapter().apply(
            OrderSubmitted(symbol="BTC_USD", order=_make_order()),
            context,
        )
        assert context.symbol("BTC_USD").recent_orders[0].order_id == "order-1"

    def test_order_filled_records_execution(self):
        context = OracleContext()
        event = OrderFilledEvent(
            order=_make_order(),
            execution=MagicMock(
                execution_price=Decimal("102"),
                executed_quantity=Decimal("1.5"),
                fee=Decimal("0.1"),
                executed_at=1_700_000_100.0,
            ),
        )
        OracleEventAdapter().apply(event, context)
        symbol_context = context.symbol("BTC_USD")
        assert symbol_context.recent_executions[0].price == Decimal("102")

    def test_position_changed_live(self):
        context = OracleContext()
        OracleEventAdapter().apply(
            PositionChanged(
                symbol="BTC_USD",
                action="BUY",
                quantity=Decimal("1.5"),
                price=Decimal("100"),
                position_qty=Decimal("1.5"),
                realized_pnl=Decimal("0"),
            ),
            context,
        )
        assert context.symbol("BTC_USD").position == Decimal("1.5")

    def test_portfolio_snapshot_updates_position(self):
        context = OracleContext()
        snapshot = PortfolioSnapshot(
            timestamp=1_700_000_000,
            cash=Decimal("9000"),
            positions={"BTC_USD": Decimal("10")},
            equity=Decimal("10000"),
        )
        OracleEventAdapter().apply(
            PortfolioSnapshotEvent(snapshot=snapshot, ticker_symbol="BTC_USD"),
            context,
        )
        assert context.symbol("BTC_USD").position == Decimal("10")


class TestOracleSummaryEvent:
    def test_implements_event(self):
        service = OracleService(MagicMock())
        summary = service.summarize()
        event = OracleSummaryEvent(summary)
        assert isinstance(event, Event)
        assert event.type == ORACLE_SUMMARY_EVENT_TYPE
        assert event.payload is summary
        assert "correlation_id" in event.to_dict()["payload"]


class TestOracleService:
    def test_observe_accumulates_and_gates_llm_calls(self):
        llm = MagicMock()
        llm.generate.return_value = "summary text"
        context = OracleContext(summary_interval=timedelta(hours=1))
        service = OracleService(llm, context)

        for _ in range(100):
            service.observe(
                MarketStateChanged(symbol="BTC_USD", price=Decimal("100"), market_timestamp=1_700_000_000.0)
            )

        assert llm.generate.call_count == 1
        assert service.get_latest_summary() is not None

    def test_summarize_if_due_returns_none_within_interval(self):
        llm = MagicMock()
        llm.generate.return_value = "summary text"
        context = OracleContext(summary_interval=timedelta(minutes=5))
        service = OracleService(llm, context)

        t0 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        assert service.summarize_if_due(t0) is not None
        assert service.summarize_if_due(t0 + timedelta(minutes=4)) is None
        assert service.summarize_if_due(t0 + timedelta(minutes=5)) is not None

    def test_publishes_summary_event(self):
        llm = MagicMock()
        llm.generate.return_value = "summary text"
        bus = MessageEventBus()
        collected = []
        bus.subscribe(ORACLE_SUMMARY_EVENT_TYPE, CallbackSubscription(collected.append))

        service = OracleService(llm, publish_bus=bus)
        service.observe(
            MarketStateChanged(symbol="BTC_USD", price=Decimal("100"), market_timestamp=1_700_000_000.0)
        )

        assert len(collected) == 1
        assert isinstance(collected[0], OracleSummaryEvent)

    def test_get_latest_summary_before_and_after(self):
        llm = MagicMock()
        llm.generate.return_value = "summary text"
        service = OracleService(llm)
        assert service.get_latest_summary() is None
        service.summarize()
        assert service.get_latest_summary() is not None

    def test_analyze_sets_context_session_and_symbol(self):
        llm = MagicMock()
        llm.generate.return_value = "analysis"
        context = OracleContext(session_id="sess-1")
        context.symbol("BTC_USD").current_price = Decimal("100")
        service = OracleService(llm, context, model="m", model_version="v1")
        summary = service.summarize()
        assert summary.summary == "analysis"
        assert summary.session_id == "sess-1"
        assert summary.symbol == "BTC_USD"
        assert summary.market_state == "active"
        assert summary.model == "m"


class TestOracleTools:
    def _service(self):
        llm = MagicMock()
        llm.generate.return_value = "tool summary"
        return OracleService(llm)

    def test_get_trading_summary_generates_when_empty(self):
        tool = GetTradingSummaryTool(oracle_service=self._service())
        result = tool._run()
        assert "tool summary" in result

    def test_analyze_trading_state(self):
        tool = AnalyzeTradingStateTool(oracle_service=self._service())
        result = tool._run()
        assert "tool summary" in result
