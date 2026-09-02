from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

from api.interfaces.asset import Asset
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction, OrderStatus
from src.backtest.backtest_clock import BacktestClock
from src.backtest.backtest_data_loader import HistoricalDataPoint
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.data.backtest_data_set import BacktestDataSet
from src.backtest.events.domain_events import OrderFilledEvent, OrderCancelledEvent
from src.backtest.execution.backtest_execution_engine import BacktestExecutionEngine
from src.backtest.execution.execution_model import ExecutionModel
from src.backtest.execution.latency.fixed_latency import FixedLatencyModel
from src.backtest.execution.slippage.fixed_tick_slippage import FixedTickSlippage
from src.backtest.execution.fees.percentage_fee import PercentageFee
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum


def _make_asset(quote_decimals: int = 2) -> Asset:
    return Asset(
        base_ticker_symbol="BTC",
        quote_ticker_symbol="USD",
        quote_decimals=quote_decimals,
        name="Bitcoin",
        exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
        min_quantity=0.001,
        quantity_decimals=3,
        schedule=0,
        candles_timeframe="MIN1",
    )


def _make_datasets(data: dict[str, list[tuple[int, str]]]) -> dict[str, BacktestDataSet]:
    """Create per-asset datasets. data = {symbol: [(timestamp, close_price), ...]}"""
    datasets: dict[str, BacktestDataSet] = {}
    for symbol, rows in data.items():
        historical_points = tuple(
            HistoricalDataPoint(
                timestamp=ts,
                open_price=Decimal(close),
                high_price=Decimal(close),
                low_price=Decimal(close),
                close_price=Decimal(close),
                volume=Decimal("1000"),
                market_cap=Decimal("0"),
            )
            for ts, close in rows
        )
        timestamps = [data_point.timestamp for data_point in historical_points]
        datasets[symbol] = BacktestDataSet(
            dataset_id=f"csv:/tmp/{symbol}",
            ticker_symbol=symbol,
            start_time=datetime.fromtimestamp(min(timestamps), tz=timezone.utc),
            end_time=datetime.fromtimestamp(max(timestamps), tz=timezone.utc),
            data_points=historical_points,
        )
    return datasets


def _make_engine(
    timestamps: dict[str, list[int]],
    data: dict[str, list[tuple[int, str]]],
    latency_ms: float = 500.0,
    slippage_ticks: int = 2,
    fee_rate: str = "0.001",
    initial_balance: str = "10000.0",
    quote_decimals: int = 2,
) -> tuple[BacktestExecutionEngine, BacktestClock, BacktestEventBus]:
    clock = BacktestClock(timestamps)
    bus = BacktestEventBus()
    datasets = _make_datasets(data)
    assets = {symbol: _make_asset(quote_decimals) for symbol in data.keys()}
    model = ExecutionModel(
        latency=FixedLatencyModel(latency_ms),
        slippage=FixedTickSlippage(slippage_ticks),
        fees=PercentageFee(Decimal(fee_rate)),
    )
    engine = BacktestExecutionEngine(
        clock=clock,
        datasets=datasets,
        bus=bus,
        execution_model=model,
        assets=assets,
        initial_balance=Decimal(initial_balance),
    )
    return engine, clock, bus


def _make_order(
    uuid: str = "test-order-1",
    symbol: str = "BTC_USD",
    action: TradeAction = TradeAction.BUY,
    quantity: str = "0.1",
    price: str = "100.00",
    created_time: float = 1000.0,
) -> Order:
    return Order(
        uuid=uuid,
        provider_name="BACKTEST",
        ticker_symbol=symbol,
        price=Decimal(price),
        quantity=quantity,
        trade_action=action,
        created_time=created_time,
    )


class TestExecutionEngineSubmit:  # pylint: disable=protected-access
    def test_submit_creates_pending_order(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000, 2000, 3000]},
            data={"BTC_USD": [(1000, "100"), (2000, "101"), (3000, "102")]},
            latency_ms=0.0,
        )
        order = _make_order(created_time=1000.0)
        engine.submit(order, "BTC_USD")

        assert len(engine._pending["BTC_USD"]) == 1
        pending = engine._pending["BTC_USD"][0]
        assert pending.order_uuid == "test-order-1"
        assert pending.eligible_at == 1000.0
        assert pending.execution_timestamp == 1000

    def test_submit_with_latency_resolves_tick(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000, 2000, 3000]},
            data={"BTC_USD": [(1000, "100"), (2000, "101"), (3000, "102")]},
            latency_ms=1500.0,
        )
        order = _make_order(created_time=1000.0)
        engine.submit(order, "BTC_USD")

        pending = engine._pending["BTC_USD"][0]
        assert pending.eligible_at == 1000.0 + 1.5
        assert pending.execution_timestamp == 2000

    def test_submit_past_end_resolves_none(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000, 2000]},
            data={"BTC_USD": [(1000, "100"), (2000, "101")]},
            latency_ms=2000000.0,
        )
        order = _make_order(created_time=1000.0)
        engine.submit(order, "BTC_USD")

        pending = engine._pending["BTC_USD"][0]
        assert pending.execution_timestamp is None


class TestExecutionEngineProcess:
    def test_zero_latency_fills_on_same_tick(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000, 2000, 3000]},
            data={"BTC_USD": [(1000, "100"), (2000, "101"), (3000, "102")]},
            latency_ms=0.0,
            slippage_ticks=0,
            fee_rate="0",
        )
        order = _make_order(created_time=1000.0)
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 1000)

        assert order.status == OrderStatus.COMPLETED
        assert order.executed_time == 1000.0
        assert len(engine.results) == 1
        assert engine.results[0].execution_price == Decimal("100")

    def test_latency_delays_fill(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000, 2000, 3000]},
            data={"BTC_USD": [(1000, "100"), (2000, "101"), (3000, "102")]},
            latency_ms=1500.0,
            slippage_ticks=0,
            fee_rate="0",
        )
        order = _make_order(created_time=1000.0)
        engine.submit(order, "BTC_USD")

        engine.process("BTC_USD", 1000)
        assert order.status == OrderStatus.PENDING

        engine.process("BTC_USD", 2000)
        assert order.status == OrderStatus.COMPLETED
        assert order.executed_time == 2000.0

        engine.process("BTC_USD", 3000)
        assert order.status == OrderStatus.COMPLETED

    def test_slippage_applied_to_buy(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000]},
            data={"BTC_USD": [(1000, "100")]},
            latency_ms=0.0,
            slippage_ticks=2,
            fee_rate="0",
            quote_decimals=2,
        )
        order = _make_order(action=TradeAction.BUY, price="100.00")
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 1000)

        result = engine.results[0]
        assert result.market_price == Decimal("100")
        assert result.execution_price == Decimal("100.02")
        assert result.slippage_per_unit == Decimal("0.02")

    def test_slippage_applied_to_sell(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000]},
            data={"BTC_USD": [(1000, "100")]},
            latency_ms=0.0,
            slippage_ticks=2,
            fee_rate="0",
            quote_decimals=2,
        )
        order = _make_order(action=TradeAction.SELL, price="100.00")
        engine.account.positions["BTC_USD"] = Decimal("1.0")
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 1000)

        result = engine.results[0]
        assert result.execution_price == Decimal("99.98")

    def test_fee_deducted_on_buy(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000]},
            data={"BTC_USD": [(1000, "100")]},
            latency_ms=0.0,
            slippage_ticks=0,
            fee_rate="0.001",
        )
        order = _make_order(quantity="1.0", price="100.00")
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 1000)

        result = engine.results[0]
        assert result.fee == Decimal("0.100")
        assert engine.account.balance_usd == Decimal("10000.0") - Decimal("100.0") - Decimal("0.100")

    def test_order_fees_and_fill_price_populated_on_fill(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000]},
            data={"BTC_USD": [(1000, "100")]},
            latency_ms=0.0,
            slippage_ticks=2,
            fee_rate="0.001",
            quote_decimals=2,
        )
        order = _make_order(quantity="1.0", price="100.00")
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 1000)

        assert order.fees == Decimal("0.10002")
        assert order.fill_price == Decimal("100.02")

    def test_fee_deducted_on_sell(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000]},
            data={"BTC_USD": [(1000, "100")]},
            latency_ms=0.0,
            slippage_ticks=0,
            fee_rate="0.001",
        )
        engine.account.positions["BTC_USD"] = Decimal("1.0")
        order = _make_order(action=TradeAction.SELL, quantity="1.0", price="100.00")
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 1000)

        result = engine.results[0]
        assert result.fee == Decimal("0.100")
        assert engine.account.balance_usd == Decimal("10000.0") + Decimal("100.0") - Decimal("0.100")

    def test_insufficient_funds_cancels_order(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000]},
            data={"BTC_USD": [(1000, "100")]},
            latency_ms=0.0,
            slippage_ticks=0,
            fee_rate="0",
            initial_balance="50.0",
        )
        order = _make_order(quantity="1.0", price="100.00")
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 1000)

        assert order.status == OrderStatus.CANCELLED
        assert len(engine.results) == 0

    def test_insufficient_position_cancels_sell(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000]},
            data={"BTC_USD": [(1000, "100")]},
            latency_ms=0.0,
            slippage_ticks=0,
            fee_rate="0",
        )
        order = _make_order(action=TradeAction.SELL, quantity="1.0", price="100.00")
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 1000)

        assert order.status == OrderStatus.CANCELLED

    def test_no_data_cancels_order(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000, 2000]},
            data={"BTC_USD": [(1000, "100")]},
            latency_ms=1500.0,
        )
        order = _make_order(created_time=1000.0)
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 2000)

        assert order.status == OrderStatus.CANCELLED

    def test_publishes_fill_event(self):
        engine, _, bus = _make_engine(
            timestamps={"BTC_USD": [1000]},
            data={"BTC_USD": [(1000, "100")]},
            latency_ms=0.0,
            slippage_ticks=0,
            fee_rate="0",
        )
        fill_callback = Mock()
        bus.subscribe_callback(OrderFilledEvent, fill_callback)

        order = _make_order()
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 1000)

        assert fill_callback.called
        event = fill_callback.call_args[0][0]
        assert event.order.uuid == "test-order-1"

    def test_publishes_cancel_event(self):
        engine, _, bus = _make_engine(
            timestamps={"BTC_USD": [1000]},
            data={"BTC_USD": [(1000, "100")]},
            latency_ms=0.0,
            initial_balance="50.0",
        )
        cancel_callback = Mock()
        bus.subscribe_callback(OrderCancelledEvent, cancel_callback)

        order = _make_order(quantity="1.0", price="100.00")
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 1000)

        assert cancel_callback.called

    def test_single_order_no_duplicates(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000]},
            data={"BTC_USD": [(1000, "100")]},
            latency_ms=0.0,
            slippage_ticks=0,
            fee_rate="0",
        )
        order = _make_order()
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 1000)

        orders_with_uuid = [o for o in engine.account.orders if o.uuid == "test-order-1"]
        assert len(orders_with_uuid) == 1
        assert orders_with_uuid[0].status == OrderStatus.COMPLETED

    def test_determinism(self):
        def run_once():
            engine, _, _ = _make_engine(
                timestamps={"BTC_USD": [1000, 2000, 3000]},
                data={"BTC_USD": [(1000, "100"), (2000, "101"), (3000, "102")]},
                latency_ms=1500.0,
                slippage_ticks=2,
                fee_rate="0.001",
            )
            order = _make_order(quantity="0.5", price="100.00")
            engine.submit(order, "BTC_USD")
            engine.process("BTC_USD", 1000)
            engine.process("BTC_USD", 2000)
            engine.process("BTC_USD", 3000)
            return engine.account.balance_usd, engine.account.positions.copy()

        balance1, positions1 = run_once()
        balance2, positions2 = run_once()
        assert balance1 == balance2
        assert positions1 == positions2


class TestExecutionEnginePendingOrders:
    def test_get_pending_orders(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000, 2000]},
            data={"BTC_USD": [(1000, "100"), (2000, "101")]},
            latency_ms=1500.0,
        )
        order = _make_order()
        engine.submit(order, "BTC_USD")

        pending = engine.get_pending_orders("BTC_USD")
        assert len(pending) == 1
        assert pending[0].uuid == "test-order-1"
        assert pending[0].status == OrderStatus.PENDING

    def test_get_pending_orders_filters_by_symbol(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000], "ETH_USD": [1000]},
            data={"BTC_USD": [(1000, "100")], "ETH_USD": [(1000, "50")]},
            latency_ms=1500.0,
        )
        order1 = _make_order(uuid="order-1", symbol="BTC_USD")
        order2 = _make_order(uuid="order-2", symbol="ETH_USD")
        engine.submit(order1, "BTC_USD")
        engine.submit(order2, "ETH_USD")

        btc_pending = engine.get_pending_orders("BTC_USD")
        assert len(btc_pending) == 1
        assert btc_pending[0].uuid == "order-1"


class TestExecutionEngineNoLookahead:
    def test_fill_uses_signal_tick_data_not_next_tick(self):
        # Signal at 1000 (zero latency); tick 2000 has a far higher price. The fill
        # must read tick 1000's data, never 2000's.
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000, 2000]},
            data={"BTC_USD": [(1000, "100"), (2000, "999")]},
            latency_ms=0.0,
            slippage_ticks=0,
            fee_rate="0",
        )
        order = _make_order(created_time=1000.0, price="100.00")
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 2000)

        result = engine.results[0]
        assert result.executed_at == 1000.0
        assert result.market_price == Decimal("100")
        assert result.execution_price == Decimal("100")

    def test_zero_assumptions_deterministic_baseline(self):
        engine, _, _ = _make_engine(
            timestamps={"BTC_USD": [1000]},
            data={"BTC_USD": [(1000, "100")]},
            latency_ms=0.0,
            slippage_ticks=0,
            fee_rate="0",
        )
        order = _make_order(quantity="1.0", price="100.00")
        engine.submit(order, "BTC_USD")
        engine.process("BTC_USD", 1000)

        result = engine.results[0]
        assert result.execution_price == Decimal("100")
        assert result.market_price == Decimal("100")
        assert result.slippage_cost == Decimal("0")
        assert result.fee == Decimal("0")
        assert engine.account.balance_usd == Decimal("9900.0")

    def test_latency_changes_execution_outcome(self):
        def run(latency_ms):
            engine, _, _ = _make_engine(
                timestamps={"BTC_USD": [1000, 2000]},
                data={"BTC_USD": [(1000, "100"), (2000, "110")]},
                latency_ms=latency_ms,
                slippage_ticks=0,
                fee_rate="0",
            )
            order = _make_order(created_time=1000.0)
            engine.submit(order, "BTC_USD")
            engine.process("BTC_USD", 1000)
            engine.process("BTC_USD", 2000)
            return engine.results[0]

        zero_latency = run(0.0)
        with_latency = run(1500.0)

        assert zero_latency.executed_at == 1000.0
        assert zero_latency.market_price == Decimal("100")
        assert with_latency.executed_at == 2000.0
        assert with_latency.market_price == Decimal("110")
        assert with_latency.market_price != zero_latency.market_price
