from decimal import Decimal
from unittest.mock import Mock

import pytest

from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.backtest_rest_service import BacktestRestService
from src.backtest.events.domain_events import OrderFilledEvent, BalanceUpdateEvent
from src.backtest.execution.backtest_execution_engine import BacktestExecutionEngine
from src.backtest.execution.execution_model import ExecutionModel
from src.backtest.execution.latency.fixed_latency import FixedLatencyModel
from src.backtest.execution.slippage.fixed_tick_slippage import FixedTickSlippage
from src.backtest.execution.fees.percentage_fee import PercentageFee
from api.interfaces.asset import Asset
from api.interfaces.order import OrderStatus
from api.interfaces.trade_action import TradeAction
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum


class TestBacktestRestService:
    @pytest.fixture
    def event_bus(self):
        return BacktestEventBus()

    @pytest.fixture
    def mock_clock(self):
        clock = Mock()
        clock.now.return_value = 1234567890
        clock.next_timestamp_at_or_after.return_value = 1234567890
        return clock

    @pytest.fixture
    def engine(self, event_bus, mock_clock):
        assets = {
            "btc-usd": Asset(
                base_ticker_symbol="BTC",
                quote_ticker_symbol="USD",
                quote_decimals=2,
                name="Bitcoin",
                exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
                min_quantity=0.001,
                quantity_decimals=3,
                schedule=0,
                candles_timeframe="MIN1",
            )
        }
        loader = Mock()
        dp = Mock()
        dp.close_price = Decimal("50000.0")
        dp.high_price = Decimal("50000.0")
        dp.low_price = Decimal("50000.0")
        dp.volume = Decimal("1000")
        dp.timestamp = 1234567890
        loader.get_data.return_value = dp
        model = ExecutionModel(
            latency=FixedLatencyModel(0.0),
            slippage=FixedTickSlippage(0),
            fees=PercentageFee(Decimal("0")),
        )
        return BacktestExecutionEngine(
            clock=mock_clock,
            loader=loader,
            bus=event_bus,
            execution_model=model,
            assets=assets,
            initial_balance=Decimal("10000.0"),
        )

    @pytest.fixture
    def provider(self, event_bus, mock_clock, engine):
        return BacktestRestService(
            event_bus=event_bus, clock=mock_clock,
            data_loader=Mock(), execution_engine=engine,
        )

    def test_place_buy_order(self, provider, engine):
        builder = provider.builder().create_order(
            uuid="123",
            ticker_symbol="btc-usd",
            quantity="0.1",
            price=Decimal("50000.0"),
            trade_action=TradeAction.BUY,
        )
        order = provider.execute(builder)

        assert order.status == OrderStatus.PENDING
        assert order.ticker_symbol == "btc-usd"
        assert len(engine.get_pending_orders("btc-usd")) == 1

    def test_order_lifecycle_through_engine(self, provider, engine, event_bus):
        order_callback = Mock()
        balance_callback = Mock()
        event_bus.subscribe_callback(OrderFilledEvent, order_callback)
        event_bus.subscribe_callback(BalanceUpdateEvent, balance_callback)

        builder = provider.builder().create_order(
            uuid="valid-buy",
            ticker_symbol="btc-usd",
            quantity="0.1",
            price=Decimal("10000.0"),
            trade_action=TradeAction.BUY,
        )
        order = provider.execute(builder)
        assert order.status == OrderStatus.PENDING

        engine.process("btc-usd", 1234567890)

        assert order.status == OrderStatus.COMPLETED
        # Fill uses market data price (50000.0) not order price (10000.0)
        assert provider.account.balance_usd == Decimal("5000.0")
        assert provider.account.positions["btc-usd"] == Decimal("0.1")
        assert order_callback.called
        assert balance_callback.called

    def test_get_account_balance(self, provider):
        balances = provider.execute(provider.builder().account_balance())
        assert balances[0].available_balance == Decimal("10000.0")

    def test_get_open_orders(self, provider):
        builder = provider.builder().create_order(
            uuid="order-1",
            ticker_symbol="btc-usd",
            quantity="0.1",
            price=Decimal("50000.0"),
            trade_action=TradeAction.BUY,
        )
        provider.execute(builder)

        open_orders = provider.execute(provider.builder().get_open_orders("btc-usd"))
        assert len(open_orders) == 1
        assert open_orders[0].uuid == "order-1"
