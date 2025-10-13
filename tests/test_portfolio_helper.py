from unittest import TestCase
from uuid import uuid4

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
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
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="0.5",
                trade_action=TradeAction.BUY,
                created_time=0.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="90.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_portfolio_value(
            available_balance=1000.0, current_price="110.0",
            open_positions=open_positions
        )

        self.assertEqual(result, 1165.0)

    def test_portfolio_value_with_closed_sell_positions(self):
        open_positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="120.0",
                quantity="0.5",
                trade_action=TradeAction.BUY,
                created_time=0.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="115.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=0.0,
            ),
        ]

        result = PortfolioHelper.calculate_portfolio_value(
            available_balance=1000.0,
            current_price="110.0",
            open_positions=open_positions
        )

        self.assertEqual(result, 1165.0)

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
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=0.0,
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
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=0.0,
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
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.SELL,
                created_time=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="110.0",
            open_positions=[],
            close_positions=close_positions
        )
        self.assertEqual(result, 10.0)

    def test_unrealized_pnl_with_closed_sell_positions_loss(self):
        close_positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.SELL,
                created_time=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="90.0",
            open_positions=[],
            close_positions=close_positions
        )
        self.assertEqual(result, -10.0)

    def test_unrealized_pnl_mixed_positions(self):
        open_positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=0.0,
            ),
        ]
        close_positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="90.0",
                quantity="0.5",
                trade_action=TradeAction.SELL,
                created_time=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="105.0",
            open_positions=open_positions,
            close_positions=close_positions
        )
        self.assertEqual(result, 12.5)

    def test_unrealized_pnl_ignores_open_sell(self):
        open_positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=0.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="110.0",
                quantity="2.0",
                trade_action=TradeAction.SELL,  # Should be ignored
                created_time=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="105.0",
            open_positions=open_positions,
            close_positions=[]
        )
        self.assertEqual(result, 5.0)

    def test_unrealized_pnl_ignores_closed_buy(self):
        close_positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.SELL,
                created_time=0.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="90.0",
                quantity="2.0",
                trade_action=TradeAction.BUY,  # Should be ignored
                created_time=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="105.0",
            open_positions=[],
            close_positions=close_positions
        )
        self.assertEqual(result, 5.0)

    def test_unrealized_pnl_multiple_positions(self):
        open_positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=0.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="110.0",
                quantity="0.5",
                trade_action=TradeAction.BUY,
                created_time=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=1000.0,
            current_price="105.0",
            open_positions=open_positions,
            close_positions=[]
        )
        self.assertEqual(result, 2.5)

    def test_unrealized_pnl_zero_starting_balance(self):
        open_positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=0.0,
            ),
        ]
        result = PortfolioHelper.calculate_unrealized_pnl_value(
            starting_balance=0.0,
            current_price="110.0",
            open_positions=open_positions,
            close_positions=[]
        )
        self.assertEqual(result, 10.0)

    def test_peak_value_no_positions(self):
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            positions=[]
        )
        self.assertEqual(result, (1000.0, 0))

    def test_peak_value_single_position(self):
        positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.SELL,
                created_time=123.0,
            ),
        ]
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            positions=positions
        )
        self.assertEqual(result, (1000.0, 0))

    def test_peak_value_increasing_portfolio(self):
        positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.SELL,
                created_time=100.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.SELL,
                created_time=200.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.SELL,
                created_time=300.0,
            ),
        ]
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            positions=positions
        )
        self.assertEqual(result, (1200.0, 200.0))

    def test_peak_value_decreasing_then_increasing(self):
        positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=100.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="150.0",
                quantity="2.0",
                trade_action=TradeAction.SELL,
                created_time=200.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="50.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=300.0,
            ),
        ]
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            positions=positions
        )
        self.assertEqual(result, (1200.0, 200.0))

    def test_peak_value_excludes_last_position(self):
        positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.SELL,
                created_time=100.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="1000.0",
                quantity="10.0",
                trade_action=TradeAction.SELL,  # This should be excluded
                created_time=200.0,
            ),
        ]
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            positions=positions
        )
        self.assertEqual(result, (1100.0, 100.0))

    def test_peak_value_with_negative_balance(self):
        positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="2000.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=100.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.SELL,
                created_time=200.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="50.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=300.0,
            ),
        ]
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            positions=positions
        )
        self.assertEqual(result, (1000.0, 0))

    def test_peak_value_stays_at_starting(self):
        positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=100.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=200.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=300.0,
            ),
        ]
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=1000.0,
            positions=positions
        )
        self.assertEqual(result, (1000.0, 0))

    def test_peak_value_with_zero_starting_balance(self):
        positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.SELL,
                created_time=100.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="50.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=200.0,
            ),
        ]
        result = PortfolioHelper.calculate_peak_value(
            starting_balance=0.0,
            positions=positions
        )
        self.assertEqual(result, (100.0, 100.0))

    def test_trough_value_no_positions(self):
        result = PortfolioHelper.calculate_trough_value(
            starting_balance=1000.0,
            positions=[]
        )
        self.assertEqual(result, (1000.0, 0.0))

    def test_trough_value_decreasing_portfolio(self):
        positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=0.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=1.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.BUY,
                created_time=2.0,
            ),
        ]
        result = PortfolioHelper.calculate_trough_value(
            starting_balance=1000.0,
            positions=positions
        )
        self.assertEqual(result, (700.0, 2.0))

    def test_trough_value_increasing_portfolio(self):
        positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.SELL,
                created_time=0.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="1.0",
                trade_action=TradeAction.SELL,
                created_time=1.0,
            ),
        ]
        result = PortfolioHelper.calculate_trough_value(
            starting_balance=1000.0,
            positions=positions
        )
        self.assertEqual(result, (1000.0, 0.0))

    def test_trough_value_with_recovery(self):
        positions = [
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="100.0",
                quantity="5.0",
                trade_action=TradeAction.BUY,
                created_time=0.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="150.0",
                quantity="2.0",
                trade_action=TradeAction.SELL,
                created_time=0.0,
            ),
            Order(
                uuid=uuid4(),
                provider_name="TEST",
                ticker_symbol="XYZ",
                price="150.0",
                quantity="2.0",
                trade_action=TradeAction.SELL,
                created_time=1.0,
            ),
        ]
        result = PortfolioHelper.calculate_trough_value(
            starting_balance=1000.0,
            positions=positions
        )
        self.assertEqual(result, (500.0, 0.0))
