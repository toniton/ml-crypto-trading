import unittest
from decimal import Decimal
from queue import Queue
from unittest.mock import MagicMock

from api.interfaces.account_balance import AccountBalance
from api.interfaces.market_data import MarketData
from api.interfaces.trading_context import TradingContext
from src.trading.managers.manager_container import ManagerContainer
from src.trading.trading_executor import TradingExecutor


class TestDynamicQuantity(unittest.TestCase):
    def _setup_executor(self, dynamic_quantity=None):
        assets = []
        manager_container = MagicMock(spec=ManagerContainer)
        activity_queue = Queue()

        self.account_manager = MagicMock()
        self.market_data_manager = MagicMock()
        self.session_manager = MagicMock()
        self.consensus_manager = MagicMock()
        self.fees_manager = MagicMock()
        self.order_manager = MagicMock()
        self.protection_manager = MagicMock()
        self.websocket_manager = MagicMock()

        manager_container.account_manager = self.account_manager
        manager_container.market_data_manager = self.market_data_manager
        manager_container.session_manager = self.session_manager
        manager_container.consensus_manager = self.consensus_manager
        manager_container.fees_manager = self.fees_manager
        manager_container.order_manager = self.order_manager
        manager_container.protection_manager = self.protection_manager
        manager_container.websocket_manager = self.websocket_manager

        executor = TradingExecutor(assets, manager_container, activity_queue, dynamic_quantity=dynamic_quantity)

        return executor, manager_container

    def test_calculate_quantity_no_dynamic_quantity(self):
        executor, _ = self._setup_executor()

        asset = MagicMock()
        asset.min_quantity = 0.001
        asset.quantity_decimals = 3
        market_data = MarketData(
            volume=Decimal("100"),
            high_price=Decimal("110"),
            low_price=Decimal("90"),
            close_price=Decimal("100"),
            timestamp=123456789.0
        )

        self.assertEqual(executor._calculate_quantity(asset, market_data), Decimal("0.001"))

    def test_calculate_quantity_with_dynamic_quantity(self):
        executor, _ = self._setup_executor(dynamic_quantity="volume / 1000")

        asset = MagicMock()
        asset.min_quantity = 0.001
        asset.quantity_decimals = 3
        asset.exchange.value = "test_exchange"
        asset.ticker_symbol = "BTC_USD"
        asset.key = 1

        market_data = MarketData(
            volume=Decimal("100"),
            high_price=Decimal("110"),
            low_price=Decimal("90"),
            close_price=Decimal("100"),
            timestamp=123456789.0
        )

        self.account_manager.get_quote_balance.return_value = AccountBalance("USD", Decimal("1000"))
        self.session_manager.get_trading_context.return_value = TradingContext("BTC_USD", "test_exchange",
                                                                               Decimal("1000"))
        self.market_data_manager.get_candles.return_value = []
        self.consensus_manager.get_consensus_score.return_value = 0.5

        # 100 / 1000 = 0.1
        self.assertEqual(executor._calculate_quantity(asset, market_data), Decimal("0.1"))

    def test_calculate_quantity_complex_expression(self):
        # Use max of min_quantity and some logic
        executor, _ = self._setup_executor(dynamic_quantity="avg(close, high, low) / 100")

        asset = MagicMock()
        asset.min_quantity = 0.001
        asset.quantity_decimals = 3
        asset.exchange.value = "test_exchange"
        asset.ticker_symbol = "BTC_USD"
        asset.key = 1

        market_data = MarketData(
            volume=Decimal("100"),
            high_price=Decimal("110"),
            low_price=Decimal("90"),
            close_price=Decimal("100"),
            timestamp=123456789.0
        )

        self.account_manager.get_quote_balance.return_value = AccountBalance("USD", Decimal("1000"))
        self.session_manager.get_trading_context.return_value = TradingContext("BTC_USD", "test_exchange",
                                                                               Decimal("1000"))
        self.market_data_manager.get_candles.return_value = []
        self.consensus_manager.get_consensus_score.return_value = 0.5

        # avg(100, 110, 90) = 100
        # 100 / 100 = 1.0
        self.assertEqual(executor._calculate_quantity(asset, market_data), Decimal("1.0"))

    def test_calculate_quantity_full_context(self):
        # Test balance and pnl (sell side or simulation)
        executor, _ = self._setup_executor(dynamic_quantity="balance + pnl + equity")

        asset = MagicMock()
        asset.min_quantity = 0.001
        asset.quantity_decimals = 3
        asset.exchange.value = "test_exchange"
        asset.ticker_symbol = "BTC_USD"
        asset.key = 1

        market_data = MarketData(
            volume=Decimal("100"),
            high_price=Decimal("110"),
            low_price=Decimal("90"),
            close_price=Decimal("100"),
            timestamp=123456789.0
        )

        self.account_manager.get_quote_balance.return_value = AccountBalance("USD", Decimal("1000"))
        ctx = TradingContext("BTC_USD", "test_exchange", Decimal("1000"))
        ctx.position_qty = Decimal("1")
        ctx.avg_entry_price = Decimal("90")
        self.session_manager.get_trading_context.return_value = ctx
        self.market_data_manager.get_candles.return_value = []
        self.consensus_manager.get_consensus_score.return_value = 0.8

        # balance(1000) + pnl(10) + equity(1100) = 2110
        self.assertEqual(executor._calculate_quantity(asset, market_data), Decimal("2110.0"))

    def test_calculate_quantity_with_error_falls_back(self):
        executor, _ = self._setup_executor(dynamic_quantity="unknown_var + 1")

        asset = MagicMock()
        asset.min_quantity = 0.001
        asset.quantity_decimals = 3
        asset.exchange.value = "test_exchange"
        asset.ticker_symbol = "BTC_USD"
        asset.key = 1

        market_data = MarketData(
            volume=Decimal("100"),
            high_price=Decimal("110"),
            low_price=Decimal("90"),
            close_price=Decimal("100"),
            timestamp=123456789.0
        )

        self.account_manager.get_quote_balance.return_value = AccountBalance("USD", Decimal("1000"))
        self.session_manager.get_trading_context.return_value = TradingContext("BTC_USD", "test_exchange",
                                                                               Decimal("1000"))
        self.market_data_manager.get_candles.return_value = []
        self.consensus_manager.get_consensus_score.return_value = 0.5

        # Should fall back to asset.min_quantity
        self.assertEqual(executor._calculate_quantity(asset, market_data), Decimal("0.001"))

    def test_calculate_quantity_with_conditionals(self):
        # Expression: (1.5 if signal > 0.5 else 1.0) * volume / 100
        executor, _ = self._setup_executor(dynamic_quantity="(1.5 if signal > 0.5 else 1.0) * volume / 100")

        asset = MagicMock()
        asset.min_quantity = 0.001
        asset.quantity_decimals = 3
        asset.exchange.value = "test_exchange"
        asset.ticker_symbol = "BTC_USD"
        asset.key = 1

        market_data = MarketData(
            volume=Decimal("100"),
            high_price=Decimal("110"),
            low_price=Decimal("90"),
            close_price=Decimal("100"),
            timestamp=123456789.0
        )

        self.account_manager.get_quote_balance.return_value = AccountBalance("USD", Decimal("1000"))
        self.session_manager.get_trading_context.return_value = TradingContext("BTC_USD", "test_exchange",
                                                                               Decimal("1000"))
        self.market_data_manager.get_candles.return_value = []

        # Test Case 1: signal > 0.5
        self.consensus_manager.get_consensus_score.return_value = 0.8
        # (1.5) * 100 / 100 = 1.5
        self.assertEqual(executor._calculate_quantity(asset, market_data), Decimal("1.5"))

        # Test Case 2: signal <= 0.5
        self.consensus_manager.get_consensus_score.return_value = 0.3
        # (1.0) * 100 / 100 = 1.0
        self.assertEqual(executor._calculate_quantity(asset, market_data), Decimal("1.0"))
