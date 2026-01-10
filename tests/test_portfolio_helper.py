from unittest import TestCase

from api.interfaces.market_data import MarketData
from src.trading.helpers.portfolio_helper import PortfolioHelper


class TestPortfolioHelper(TestCase):

    def test_portfolio_value_no_positions(self):
        result = PortfolioHelper.calculate_portfolio_value(
            available_balance=1000.0, current_price="100.0",
            open_positions=[]
        )
        self.assertEqual(result, 1000.0)

    def test_portfolio_value_with_open_buy_positions(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="0.5",
                timestamp=0.0,
            ),
            MarketData(
                low_price="90.0",
                high_price="90.0",
                close_price="90.0",
                volume="1.0",
                timestamp=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_portfolio_value(
            available_balance=1000.0, current_price="110.0",
            open_positions=open_positions
        )
        # 1000 + (2 * 110) = 1220.0 (volume ignored, each position is 1 unit)
        self.assertEqual(1220.0, result)

    def test_portfolio_value_with_closed_sell_positions(self):
        open_positions = [
            MarketData(
                low_price="120.0",
                high_price="120.0",
                close_price="120.0",
                volume="0.5",
                timestamp=0.0,
            ),
            MarketData(
                low_price="115.0",
                high_price="115.0",
                close_price="115.0",
                volume="1.0",
                timestamp=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_portfolio_value(
            available_balance=1000.0,
            current_price="110.0",
            open_positions=open_positions,
        )
        # 1000 + (2 * 110) = 1220.0
        self.assertEqual(result, 1220.0)

    def test_unrealized_pnl_no_positions(self):
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="100.0",
            open_positions=[],
            close_positions=[]
        )
        self.assertEqual(result, 0.0)

    def test_unrealized_pnl_profit_on_open_buy(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="110.0",
            open_positions=open_positions,
            close_positions=[]
        )
        self.assertEqual(result, 10.0)

    def test_unrealized_pnl_loss_on_open_buy(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="90.0",
            open_positions=open_positions,
            close_positions=[]
        )
        self.assertEqual(result, -10.0)

    def test_unrealized_pnl_with_closed_sell_positions_profit(self):
        close_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="110.0",
            open_positions=[],
            close_positions=close_positions
        )
        self.assertEqual(result, 0.0)

    def test_unrealized_pnl_with_closed_sell_positions_loss(self):
        close_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="90.0",
            open_positions=[],
            close_positions=close_positions
        )
        self.assertEqual(0.0, result)

    def test_unrealized_pnl_mixed_positions(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=0.0,
            ),
        ]
        close_positions = [
            MarketData(
                low_price="90.0",
                high_price="90.0",
                close_price="90.0",
                volume="0.5",
                timestamp=0.5,
            ),
        ]
        # FIFO: 1 Buy(100) is closed by 1 Sell(90). Nothing remains.
        # Unrealized PnL = 0
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="105.0",
            open_positions=open_positions,
            close_positions=close_positions
        )
        self.assertEqual(0.0, result)

    def test_unrealized_pnl_ignores_open_sell(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=0.0,
            ),
            MarketData(
                low_price="110.0",
                high_price="110.0",
                close_price="110.0",
                volume="2.0",
                timestamp=1.0,
            ),
        ]
        # All are open buys.
        # PnL = (105-100) + (105-110) = 5 - 5 = 0
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="105.0",
            open_positions=open_positions,
            close_positions=[]
        )
        self.assertEqual(0.0, result)

    def test_unrealized_pnl_ignores_closed_buy(self):
        open_positions = [
            MarketData(
                low_price="110.0",
                high_price="110.0",
                close_price="110.0",
                volume="2.0",
                timestamp=0.0,
            ),
        ]
        close_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=1.0,
            ),
            MarketData(
                low_price="90.0",
                high_price="90.0",
                close_price="90.0",
                volume="1.0",
                timestamp=2.0,
            ),
        ]
        # FIFO: 1.0 of Buy(110) closed by Sell(100). Next 1.0 of Buy(110) closed by Sell(90).
        # Nothing remains.
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="105.0",
            open_positions=open_positions,
            close_positions=close_positions
        )
        self.assertEqual(0.0, result)

    def test_unrealized_pnl_multiple_positions(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=0.0,
            ),
            MarketData(
                low_price="110.0",
                high_price="110.0",
                close_price="110.0",
                volume="0.5",
                timestamp=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="105.0",
            open_positions=open_positions,
            close_positions=[]
        )
        # (105-100) + (105-110) = 5 - 5 = 0
        self.assertEqual(result, 0.0)

    def test_unrealized_pnl_zero_starting_balance(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=0.0,
            ),
        ]
        with self.assertRaises(ValueError):
            PortfolioHelper.calculate_unrealized_pnl_value(
                starting_balance=0.0,
                current_price="110.0",
                open_positions=open_positions,
                close_positions=[]
            )

    def test_peak_value_no_positions(self):
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            open_positions=[],
            closed_positions=[]
        )
        self.assertEqual(result, (1000.0, None))

    def test_peak_value_single_position(self):
        closed_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=123.0,
            ),
        ]
        # Starts at 1000. Sells for 100. New balance 1100. Peak is 1100 at time 123.
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            open_positions=[],
            closed_positions=closed_positions
        )
        self.assertEqual(result, (1100.0, 123.0))

    def test_peak_value_increasing_portfolio(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=100.0,
            ),
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=200.0,
            ),
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=300.0,
            ),
        ]
        closed_positions = [
            MarketData(
                low_price="110.0",
                high_price="110.0",
                close_price="110.0",
                volume="1.0",
                timestamp=150.0,
            ),
            MarketData(
                low_price="120.0",
                high_price="120.0",
                close_price="120.0",
                volume="1.0",
                timestamp=250.0,
            ),
            MarketData(
                low_price="130.0",
                high_price="130.0",
                close_price="130.0",
                volume="1.0",
                timestamp=350.0,
            ),
        ]
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            open_positions=open_positions,
            closed_positions=closed_positions
        )
        self.assertEqual(result, (1060.0, 350.0))

    def test_peak_value_decreasing_then_increasing(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=100.0,
            ),
            MarketData(
                low_price="50.0",
                high_price="50.0",
                close_price="50.0",
                volume="1.0",
                timestamp=300.0,
            ),
        ]
        closed_positions = [
            MarketData(
                low_price="150.0",
                high_price="150.0",
                close_price="150.0",
                volume="1.0",
                timestamp=200.0,
            ),
        ]
        # 1000 -> Buy(100)@100 -> 900. Sell(150)@200 -> 1050 (PEAK). Buy(50)@300 -> 1000.
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            open_positions=open_positions,
            closed_positions=closed_positions
        )
        self.assertEqual(result, (1050.0, 200.0))

    def test_peak_value_excludes_last_position(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="2.0",
                timestamp=100.0,
            ),
        ]
        closed_positions = [
            MarketData(
                low_price="200.0",
                high_price="200.0",
                close_price="200.0",
                volume="2.0",
                timestamp=200.0,
            ),
        ]
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            open_positions=open_positions,
            closed_positions=closed_positions
        )
        # 1000 -> Buy(100) -> 900. Sell(200) -> 1100.
        self.assertEqual((1100.0, 200.0), result)

    def test_peak_value_with_negative_balance(self):
        open_positions = [
            MarketData(
                low_price="2000.0",
                high_price="2000.0",
                close_price="2000.0",
                volume="1.0",
                timestamp=100.0,
            ),
        ]
        closed_positions = []

        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            open_positions=open_positions,
            closed_positions=closed_positions
        )
        self.assertEqual(result, (1000.0, None))

    def test_peak_value_stays_at_starting(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="100000.0",
                timestamp=100.0,
            ),
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="100000.0",
                timestamp=200.0,
            ),
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="100000.0",
                timestamp=300.0,
            ),
        ]
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            open_positions=open_positions,
            closed_positions=[]
        )
        self.assertEqual(result, (1000.0, None))

    def test_peak_value_with_zero_starting_balance(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=100.0,
            ),
        ]
        closed_positions = [
            MarketData(
                low_price="150.0",
                high_price="150.0",
                close_price="150.0",
                volume="1.0",
                timestamp=200.0,
            ),
        ]
        with self.assertRaises(ValueError):
            PortfolioHelper.calculate_peak_value(
                starting_balance=0.0,
                open_positions=open_positions,
                closed_positions=closed_positions
            )

    def test_trough_value_no_positions(self):
        result = PortfolioHelper.calculate_trough_value(
            starting_balance=1000.0,
            open_positions=[],
            closed_positions=[]
        )
        self.assertEqual(result, (1000.0, None))

    def test_trough_value_decreasing_portfolio(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=0.0,
            ),
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=1.0,
            ),
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=2.0,
            ),
        ]
        result = PortfolioHelper.calculate_trough_value(
            starting_balance=1000.0,
            open_positions=open_positions,
            closed_positions=[]
        )
        # 1000 -> Buy(100) -> 900. Buy(100) -> 800. Buy(100) -> 700.
        self.assertEqual(result, (700.0, 2.0))

    def test_trough_value_increasing_portfolio(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=0.0,
            ),
        ]
        closed_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="1.0",
                timestamp=1.0,
            ),
        ]
        result = PortfolioHelper.calculate_trough_value(
            starting_balance=1000.0,
            open_positions=open_positions,
            closed_positions=closed_positions
        )
        self.assertEqual(result, (900.0, 0.0))

    def test_trough_value_with_recovery(self):
        open_positions = [
            MarketData(
                low_price="100.0",
                high_price="100.0",
                close_price="100.0",
                volume="5.0",
                timestamp=0.0,
            ),
        ]
        closed_positions = [
            MarketData(
                low_price="150.0",
                high_price="150.0",
                close_price="150.0",
                volume="2.0",
                timestamp=1.0,
            ),
            MarketData(
                low_price="150.0",
                high_price="150.0",
                close_price="150.0",
                volume="2.0",
                timestamp=2.0,
            ),
        ]
        result = PortfolioHelper.calculate_trough_value(
            starting_balance=1000.0,
            open_positions=open_positions,
            closed_positions=closed_positions
        )
        self.assertEqual(result, (900.0, 0.0))
