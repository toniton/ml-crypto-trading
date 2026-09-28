import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.agent.oracle.events import (
    ORACLE_EVENT_TYPES,
    ORACLE_SUMMARY_EVENT_TYPE,
    OracleSummaryEvent,
)
from src.agent.oracle.oracle_adapter import OracleEventAdapter
from src.agent.oracle.oracle_context import MAX_OBSERVATIONS, OracleContext
from src.agent.oracle.oracle_service import ORACLE_SYSTEM_PROMPT, OracleService
from src.agent.oracle.oracle_summary import OracleSummary
from src.agent.oracle.oracle_tool import AnalyzeTradingStateTool, GetTradingSummaryTool
from src.server.timeline_projector import TimelineProjector
from src.backtest.domain.result import PortfolioSnapshot
from src.backtest.events.domain_events import (
    OrderFilledEvent,
    OrderSubmittedEvent,
    PortfolioSnapshotEvent,
)
from src.core.interfaces.event import Event
from src.events.message_event_bus import CallbackSubscription, MessageEventBus
from src.trading.events import (
    MarketStateChangedEvent,
    OrderSubmittedEvent as LiveOrderSubmittedEvent,
    PositionChangedEvent,
)


def _make_order(symbol: str = "BTC_USD", action: TradeAction = TradeAction.BUY) -> Order:
    return Order(
        uuid="order-1",
        provider_name="BACKTEST",
        ticker_symbol=symbol,
        price=Decimal("100"),
        quantity="1.5",
        trade_action=action,
        created_time=1_700_000_000.0,
        commit_hash="56339b9",
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
                LiveOrderSubmittedEvent(symbol="BTC_USD", order=_make_order()),
                context,
            )
        assert len(context.symbol("BTC_USD").recent_orders) == MAX_OBSERVATIONS


class TestOracleEventAdapter:
    def test_market_state_live(self):
        context = OracleContext()
        OracleEventAdapter().apply(
            MarketStateChangedEvent(symbol="BTC_USD", price=Decimal("101.5"), market_timestamp=1_700_000_000.0),
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
            LiveOrderSubmittedEvent(symbol="BTC_USD", order=_make_order()),
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
            PositionChangedEvent(
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
                MarketStateChangedEvent(symbol="BTC_USD", price=Decimal("100"), market_timestamp=1_700_000_000.0)
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
            MarketStateChangedEvent(symbol="BTC_USD", price=Decimal("100"), market_timestamp=1_700_000_000.0)
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
        llm.generate.assert_called_once()
        _, kwargs = llm.generate.call_args
        assert kwargs.get("system_prompt") == ORACLE_SYSTEM_PROMPT

    def test_oracle_event_types_has_no_duplicates(self):
        assert len(ORACLE_EVENT_TYPES) == len(set(ORACLE_EVENT_TYPES))

    def test_concurrent_events_during_slow_llm_do_not_trigger_multiple_generations(self):
        started_event = threading.Event()
        release_event = threading.Event()

        def slow_generate(_prompt, **_kwargs):
            started_event.set()
            release_event.wait(timeout=2.0)
            return "slow summary"

        llm = MagicMock()
        llm.generate.side_effect = slow_generate
        context = OracleContext(summary_interval=timedelta(hours=1))
        service = OracleService(llm, context)

        thread1 = threading.Thread(
            target=service.observe,
            args=(MarketStateChangedEvent(symbol="BTC_USD", price=Decimal("100"), market_timestamp=1_700_000_000.0),),
        )
        thread1.start()

        started_event.wait(timeout=2.0)
        assert started_event.is_set()

        for _ in range(10):
            service.observe(
                MarketStateChangedEvent(symbol="ETH_USD", price=Decimal("200"), market_timestamp=1_700_000_001.0)
            )

        release_event.set()
        thread1.join()

        assert llm.generate.call_count == 1
        assert service.get_latest_summary().summary == "slow summary"

    def test_failure_cooldown_prevents_immediate_retry_storm(self):
        llm = MagicMock()
        llm.generate.side_effect = RuntimeError("LLM error")
        context = OracleContext(summary_interval=timedelta(hours=1))
        service = OracleService(llm, context, failure_cooldown=timedelta(seconds=60))

        t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        service.observe(
            MarketStateChangedEvent(symbol="BTC_USD", price=Decimal("100"), market_timestamp=1_700_000_000.0)
        )

        # Before 60s cooldown expires, should return None
        assert service.summarize_if_due(t0 + timedelta(seconds=10)) is None
        assert service.summarize_if_due(t0 + timedelta(seconds=59)) is None
        # Once 60s cooldown passes, is_due is True and it can attempt again
        with pytest.raises(RuntimeError):
            service.summarize(t0 + timedelta(seconds=61))


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

    def test_oracle_summary_event_properties_accessible(self):
        summary = OracleSummary(
            summary="BTC is bullish",
            market_state="active",
            trading_state="flat",
            risk_state="normal",
            symbol="BTC_USD",
            session_id="sess-42",
        )
        event = OracleSummaryEvent(summary)
        assert event.summary == "BTC is bullish"
        assert event.symbol == "BTC_USD"
        assert event.market_state == "active"
        assert event.session_id == "sess-42"
        assert event.correlation_id == summary.correlation_id

    def test_oracle_summary_event_projected_into_timeline(self):
        bus = MessageEventBus()
        projector = TimelineProjector(event_bus=bus)
        projector.subscribe()

        summary = OracleSummary(
            summary="Market consolidation underway",
            market_state="active",
            trading_state="flat",
            risk_state="normal",
            symbol="CRO_USD",
        )
        event = OracleSummaryEvent(summary)
        bus.publish(event)

        items = projector.list_items(category="AGENT")
        assert len(items) == 1
        assert items[0]["title"] == "Oracle Summary: CRO_USD"
        assert items[0]["metadata"]["symbol"] == "CRO_USD"
        assert items[0]["metadata"]["summary"] == "Market consolidation underway"

    def test_get_trading_summary_queries_historical_days(self):
        bus = MessageEventBus()
        projector = TimelineProjector(event_bus=bus)
        projector.subscribe()

        summary1 = OracleSummary(
            summary="Day 1 overview",
            market_state="active",
            trading_state="flat",
            risk_state="normal",
            symbol="BTC_USD",
        )
        summary2 = OracleSummary(
            summary="Day 2 overview",
            market_state="active",
            trading_state="position_open",
            risk_state="normal",
            symbol="BTC_USD",
        )
        bus.publish(OracleSummaryEvent(summary1))
        bus.publish(OracleSummaryEvent(summary2))

        service = self._service()
        tool = GetTradingSummaryTool(oracle_service=service, timeline_projector=projector)

        res = tool._run(days=3, symbol="BTC_USD")
        assert "Found 2 Oracle trading summary event(s)" in res
        assert "Day 1 overview" in res
        assert "Day 2 overview" in res

    def test_get_trading_summary_queries_historical_days_fallback_when_empty(self):
        bus = MessageEventBus()
        projector = TimelineProjector(event_bus=bus)
        service = self._service()
        tool = GetTradingSummaryTool(oracle_service=service, timeline_projector=projector)

        res = tool._run(days=7, symbol="ETH_USD")
        assert "No historical Oracle summaries found in the past 7 day(s) for ETH_USD." in res
        assert "tool summary" in res
