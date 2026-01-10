from unittest import TestCase

from api.interfaces.market_data import MarketData
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
                MarketData(
                    low_price="500",
                    high_price="500",
                    close_price="500",
                    volume="1.0",
                    timestamp=1
                ),
                MarketData(
                    low_price="750",
                    high_price="750",
                    close_price="750",
                    volume="1.0",
                    timestamp=3
                ),
                MarketData(
                    low_price="400",
                    high_price="400",
                    close_price="400",
                    volume="1.0",
                    timestamp=5
                ),
                MarketData(
                    low_price="600",
                    high_price="600",
                    close_price="600",
                    volume="1.0",
                    timestamp=7
                ),
                MarketData(
                    low_price="350",
                    high_price="350",
                    close_price="350",
                    volume="1.0",
                    timestamp=9
                ),
            ],
            close_positions=[
                MarketData(
                    low_price="750",
                    high_price="750",
                    close_price="750",
                    volume="1.0",
                    timestamp=2
                ),
                MarketData(
                    low_price="400",
                    high_price="400",
                    close_price="400",
                    volume="1.0",
                    timestamp=4
                ),
                MarketData(
                    low_price="600",
                    high_price="600",
                    close_price="600",
                    volume="1.0",
                    timestamp=6
                ),
                MarketData(
                    low_price="350",
                    high_price="350",
                    close_price="350",
                    volume="1.0",
                    timestamp=8
                ),
                MarketData(
                    low_price="800",
                    high_price="800",
                    close_price="800",
                    volume="1.0",
                    timestamp=10
                )
            ]
        )
        trading_context.available_balance = 5
        draw_down_guard = MaxDrawDownGuard(self.config)
        assert draw_down_guard.can_trade(TradeAction.BUY, trading_context, None) is True
