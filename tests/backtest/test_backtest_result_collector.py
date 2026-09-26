from decimal import Decimal

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
    ExecutionConfiguration,
)
from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.backtest_result_collector import BacktestResultCollector
from src.backtest.domain.session import BacktestSession
from src.backtest.events.domain_events import OrderFilledEvent, OrderSubmittedEvent
from src.backtest.execution.execution_types import ExecutionResult


def _make_backtest_session(ticker_symbol: str = "BTC_USD") -> BacktestSession:
    request = BacktestRequest(
        ticker_symbol=ticker_symbol,
        data_source=BacktestDataSourceRequest(source_type=BacktestDataSourceType.CSV),
        initial_balance=Decimal("10000.0"),
        execution=ExecutionConfiguration(latency_ms=0, slippage_ticks=0, fee_rate=Decimal("0.001")),
    )
    return BacktestSession(
        id="session-1",
        ticker_symbol=ticker_symbol,
        request=request,
    )


def test_collector_computes_strategy_attribution_from_fills():
    bus = BacktestEventBus()
    collector = BacktestResultCollector(bus)

    buy_order = Order(
        uuid="buy-1",
        provider_name="BACKTEST",
        ticker_symbol="BTC_USD",
        price=Decimal("100.0"),
        quantity="1.0",
        trade_action=TradeAction.BUY,
        created_time=100.0,
        executed_time=100.0,
        status=OrderStatus.COMPLETED,
        winning_strategy="RsiOversold",
        commit_hash="abc1234",
    )
    sell_order = Order(
        uuid="sell-1",
        provider_name="BACKTEST",
        ticker_symbol="BTC_USD",
        price=Decimal("120.0"),
        quantity="1.0",
        trade_action=TradeAction.SELL,
        created_time=200.0,
        executed_time=200.0,
        status=OrderStatus.COMPLETED,
        winning_strategy="RsiOversold",
        commit_hash="abc1234",
    )

    buy_exec = ExecutionResult(
        order_uuid="buy-1",
        ticker_symbol="BTC_USD",
        trade_action=TradeAction.BUY,
        status=OrderStatus.COMPLETED,
        requested_price=Decimal("100.0"),
        market_price=Decimal("100.0"),
        execution_price=Decimal("100.0"),
        requested_quantity=Decimal("1.0"),
        executed_quantity=Decimal("1.0"),
        slippage_per_unit=Decimal("0.0"),
        slippage_cost=Decimal("0.0"),
        fee=Decimal("0.1"),
        signal_at=100.0,
        submitted_at=100.0,
        eligible_at=100.0,
        executed_at=100.0,
        commit_hash="abc1234",
    )
    sell_exec = ExecutionResult(
        order_uuid="sell-1",
        ticker_symbol="BTC_USD",
        trade_action=TradeAction.SELL,
        status=OrderStatus.COMPLETED,
        requested_price=Decimal("120.0"),
        market_price=Decimal("120.0"),
        execution_price=Decimal("120.0"),
        requested_quantity=Decimal("1.0"),
        executed_quantity=Decimal("1.0"),
        slippage_per_unit=Decimal("0.0"),
        slippage_cost=Decimal("0.0"),
        fee=Decimal("0.12"),
        signal_at=200.0,
        submitted_at=200.0,
        eligible_at=200.0,
        executed_at=200.0,
        commit_hash="abc1234",
    )

    bus.publish(OrderSubmittedEvent(order=buy_order))
    bus.publish(OrderFilledEvent(order=buy_order, execution=buy_exec))
    bus.publish(OrderSubmittedEvent(order=sell_order))
    bus.publish(OrderFilledEvent(order=sell_order, execution=sell_exec))

    session = _make_backtest_session("BTC_USD")
    result = collector.build_result(session)

    assert len(result.trades) == 1
    assert "RsiOversold" in result.strategy_attribution
    assert result.strategy_attribution["RsiOversold"].total_trades == 1
    assert result.strategy_attribution["RsiOversold"].winning_trades == 1
    assert "abc1234" in result.commit_attribution
