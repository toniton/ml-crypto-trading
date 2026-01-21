from decimal import Decimal
from unittest.mock import Mock
import pytest
from backtest.backtest_event_bus import BacktestEventBus
from backtest.backtest_rest_service import BacktestRestService
from backtest.events.domain_events import OrderFillEvent, BalanceUpdateEvent
from api.interfaces.trade_action import TradeAction
from api.interfaces.order import OrderStatus


class TestBacktestRestService:
    @pytest.fixture
    def event_bus(self):
        return BacktestEventBus()

    @pytest.fixture
    def mock_clock(self):
        clock = Mock()
        clock.now.return_value = 1234567890.0
        return clock

    @pytest.fixture
    def provider(self, event_bus, mock_clock):
        return BacktestRestService(event_bus=event_bus, clock=mock_clock, data_loader=Mock())

    def test_place_buy_order_and_events(self, provider, event_bus):
        # Mock callbacks to verify events
        order_callback = Mock()
        balance_callback = Mock()

        event_bus.subscribe(OrderFillEvent, order_callback)
        event_bus.subscribe(BalanceUpdateEvent, balance_callback)

        # Place Order (affordable)
        builder = provider.builder().create_order(
            uuid="123",
            ticker_symbol="btc-usd",
            quantity="0.1",
            price=Decimal("50000.0"),
            trade_action=TradeAction.BUY
        )
        provider.execute(builder)

        # Verify Order
        order = provider.account.orders[-1]
        assert order.status == OrderStatus.COMPLETED
        assert order.ticker_symbol == "btc-usd"
        assert provider.account.balance_usd == Decimal("10000.0") - (Decimal("50000.0") * Decimal("0.1"))

    def test_insufficient_balance(self, provider):
        builder = provider.builder().create_order(
            uuid="123",
            ticker_symbol="btc-usd",
            quantity="1.0",
            price=Decimal("50000.0"),  # 50k needed, 10k available
            trade_action=TradeAction.BUY
        )
        with pytest.raises(ValueError):
            provider.execute(builder)

    def test_place_feasible_buy_order(self, provider, event_bus):
        order_callback = Mock()
        balance_callback = Mock()
        event_bus.subscribe(OrderFillEvent, order_callback)
        event_bus.subscribe(BalanceUpdateEvent, balance_callback)

        # Buy 0.1 BTC @ 10,000 = $1,000 cost. Balance 10,000 -> 9,000.
        builder = provider.builder().create_order(
            uuid="valid-buy",
            ticker_symbol="btc-usd",
            quantity="0.1",
            price=Decimal("10000.0"),
            trade_action=TradeAction.BUY
        )
        provider.execute(builder)

        # Verify simulated state
        assert provider.account.balance_usd == Decimal("9000.0")
        assert provider.account.positions["btc-usd"] == Decimal("0.1")

        # Verify Events
        assert order_callback.called
        assert balance_callback.called

        # Verify Event Payload
        event_args = order_callback.call_args[0][0]
        assert isinstance(event_args, OrderFillEvent)
        assert event_args.order.uuid == "valid-buy"

        balance_args = balance_callback.call_args[0][0]
        assert isinstance(balance_args, BalanceUpdateEvent)
        assert balance_args.balances[0].available_balance == Decimal("9000.0")
