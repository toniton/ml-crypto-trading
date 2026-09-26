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
        assert draw_down_guard.can_trade(TradeAction.BUY, trading_context, None) is True
