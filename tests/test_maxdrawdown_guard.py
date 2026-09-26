from unittest import TestCase

from api.interfaces.position_entry import PositionEntry
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
            exchange="",
            ticker_symbol="",
            starting_balance=1500,
            open_positions=[
                PositionEntry(price=500, quantity=1.0, timestamp=1),
                PositionEntry(price=750, quantity=1.0, timestamp=3),
                PositionEntry(price=400, quantity=1.0, timestamp=5),
                PositionEntry(price=600, quantity=1.0, timestamp=7),
                PositionEntry(price=350, quantity=1.0, timestamp=9),
            ],
            close_positions=[
                PositionEntry(price=750, quantity=1.0, timestamp=2),
                PositionEntry(price=400, quantity=1.0, timestamp=4),
                PositionEntry(price=600, quantity=1.0, timestamp=6),
                PositionEntry(price=350, quantity=1.0, timestamp=8),
                PositionEntry(price=800, quantity=1.0, timestamp=10),
            ]
        )
        trading_context.available_balance = 5
        draw_down_guard = MaxDrawDownGuard(self.config)
        self.assertTrue(draw_down_guard.can_trade(TradeAction.BUY, trading_context, None))

    def test_can_trade_sell_always_permitted(self):
        trading_context = TradingContext(
            exchange="",
            ticker_symbol="",
            starting_balance=1000,
        )
        draw_down_guard = MaxDrawDownGuard(self.config)
        self.assertTrue(draw_down_guard.can_trade(TradeAction.SELL, trading_context, None))

    def test_can_trade_returns_false_when_starting_balance_zero(self):
        trading_context = TradingContext(
            exchange="",
            ticker_symbol="",
            starting_balance=0,
        )
        draw_down_guard = MaxDrawDownGuard(self.config)
        self.assertFalse(draw_down_guard.can_trade(TradeAction.BUY, trading_context, None))

    def test_can_trade_returns_false_when_drawdown_exceeds_threshold(self):
        strict_config = GuardConfig(
            cooldown_timeout=100,
            max_drawdown_percentage=0.2,
            max_drawdown_period=10
        )
        trading_context = TradingContext(
            exchange="",
            ticker_symbol="",
            starting_balance=1000,
            open_positions=[
                PositionEntry(price=500, quantity=1.0, timestamp=1),
            ],
            close_positions=[
                PositionEntry(price=200, quantity=1.0, timestamp=2),
            ]
        )
        draw_down_guard = MaxDrawDownGuard(strict_config)
        self.assertFalse(draw_down_guard.can_trade(TradeAction.BUY, trading_context, None))

    def test_can_trade_honors_rolling_period_window(self):
        rolling_config = GuardConfig(
            cooldown_timeout=100,
            max_drawdown_percentage=0.2,
            max_drawdown_period=2
        )
        trading_context = TradingContext(
            exchange="",
            ticker_symbol="",
            starting_balance=1000,
            open_positions=[
                PositionEntry(price=500, quantity=1.0, timestamp=1),
                PositionEntry(price=100, quantity=1.0, timestamp=3),
            ],
            close_positions=[
                PositionEntry(price=200, quantity=1.0, timestamp=2),
                PositionEntry(price=100, quantity=1.0, timestamp=4),
            ]
        )
        draw_down_guard = MaxDrawDownGuard(rolling_config)
        self.assertTrue(draw_down_guard.can_trade(TradeAction.BUY, trading_context, None))
