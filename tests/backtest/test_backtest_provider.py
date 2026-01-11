from decimal import Decimal
from unittest.mock import Mock
import pytest
from backtest.backtest_event_bus import BacktestEventBus
from backtest.backtest_exchange_rest_client import BacktestExchangeRestClient
from backtest.events import OrderFillEvent, BalanceUpdateEvent
from api.interfaces.trade_action import TradeAction
from api.interfaces.order import OrderStatus


class TestBacktestExchangeRestClient:
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
        return BacktestExchangeRestClient(event_bus=event_bus, clock=mock_clock)

    def test_place_buy_order_and_events(self, provider, event_bus):
        # Mock callbacks to verify events
        order_callback = Mock()
        balance_callback = Mock()

        event_bus.subscribe(OrderFillEvent, order_callback)
        event_bus.subscribe(BalanceUpdateEvent, balance_callback)

        # Place Order (affordable)
        order = provider.place_order(
            uuid="123",
            ticker_symbol="btc-usd",
            quantity="0.1",
            price=Decimal("50000.0"),
            trade_action=TradeAction.BUY
        )

        # Verify Order
        assert order.status == OrderStatus.COMPLETED
        assert order.ticker_symbol == "btc-usd"
        assert provider.account.balance_usd == Decimal("10000.0") - (Decimal("50000.0") * Decimal("0.1"))

    def test_insufficient_balance(self, provider):
        with pytest.raises(ValueError):
            provider.place_order(
                uuid="123",
                ticker_symbol="btc-usd",
                quantity="1.0",
                price=Decimal("50000.0"),  # 50k needed, 10k available
                trade_action=TradeAction.BUY
            )

    def test_place_feasible_buy_order(self, provider, event_bus):
        order_callback = Mock()
        balance_callback = Mock()
        event_bus.subscribe(OrderFillEvent, order_callback)
        event_bus.subscribe(BalanceUpdateEvent, balance_callback)

        # Buy 0.1 BTC @ 10,000 = $1,000 cost. Balance 10,000 -> 9,000.
        _order = provider.place_order(
            uuid="valid-buy",
            ticker_symbol="btc-usd",
            quantity="0.1",
            price=Decimal("10000.0"),
            trade_action=TradeAction.BUY
        )

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
