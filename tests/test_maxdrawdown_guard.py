from unittest import TestCase

from uuid import uuid4

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.configuration.guard_config import GuardConfig
from src.trading.protection.guards.maxdrawdown_guard import MaxDrawDownGuard


class MaxDrawDownGuardTest(TestCase):
    config = GuardConfig(
        cooldown_timeout=100,
        max_drawdown_percentage=0.6,
        max_drawdown_period=10
    )

    def test_can_trade(self):
        trading_context = TradingContext(
            starting_balance=1500,
            open_positions=[
                Order(
                    provider_name="",
                    price="500",
                    quantity="1",
                    ticker_symbol="",
                    trade_action=TradeAction.BUY,
                    uuid=str(uuid4()),
                    created_time=1
                ),
                Order(
                    provider_name="",
                    price="750",
                    quantity="1",
                    ticker_symbol="",
                    trade_action=TradeAction.BUY,
                    uuid=str(uuid4()),
                    created_time=3
                ),
                Order(
                    provider_name="",
                    price="400",
                    quantity="1",
                    ticker_symbol="",
                    trade_action=TradeAction.BUY,
                    uuid=str(uuid4()),
                    created_time=5
                ),
                Order(
                    provider_name="",
                    price="600",
                    quantity="1",
                    ticker_symbol="",
                    trade_action=TradeAction.BUY,
                    uuid=str(uuid4()),
                    created_time=7
                ),
                Order(
                    provider_name="",
                    price="350",
                    quantity="1",
                    ticker_symbol="",
                    trade_action=TradeAction.BUY,
                    uuid=str(uuid4()),
                    created_time=9
                )
            ],
            close_positions=[
                Order(
                    provider_name="",
                    price="750",
                    quantity="1",
                    ticker_symbol="",
                    trade_action=TradeAction.SELL,
                    uuid=str(uuid4()),
                    created_time=2
                ),
                Order(
                    provider_name="",
                    price="400",
                    quantity="1",
                    ticker_symbol="",
                    trade_action=TradeAction.SELL,
                    uuid=str(uuid4()),
                    created_time=4
                ),
                Order(
                    provider_name="",
                    price="600",
                    quantity="1",
                    ticker_symbol="",
                    trade_action=TradeAction.SELL,
                    uuid=str(uuid4()),
                    created_time=6
                ),
                Order(
                    provider_name="",
                    price="350",
                    quantity="1",
                    ticker_symbol="",
                    trade_action=TradeAction.SELL,
                    uuid=str(uuid4()),
                    created_time=8
                ),
                Order(
                    provider_name="",
                    price="800",
                    quantity="1",
                    ticker_symbol="",
                    trade_action=TradeAction.SELL,
                    uuid=str(uuid4()),
                    created_time=10
                )
            ]
        )
        trading_context.available_balance = 5
        draw_down_guard = MaxDrawDownGuard(self.config)
        assert draw_down_guard.can_trade(TradeAction.BUY, trading_context) is True


