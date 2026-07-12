import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.trading_context import TradingContext
from src.llm.tools.exchange_fees_tool import ExchangeFeesTool
from src.llm.tools.market_statistics_tool import MarketStatisticsTool
from src.llm.tools.trading_context_tool import TradingContextTool, format_decimal
from src.trading.fees.fees_manager import FeesManager
from src.trading.markets.market_data_manager import MarketDataManager


class TestTradingContextTool(unittest.TestCase):
    def test_format_decimal(self):
        self.assertEqual(format_decimal(Decimal('7.8E-7')), '0.00000078')
        self.assertEqual(format_decimal(Decimal('0.000000')), '0')
        self.assertEqual(format_decimal(Decimal('1.5000')), '1.5')
        self.assertEqual(format_decimal(Decimal('100.0')), '100')
        self.assertEqual(format_decimal(Decimal('inf')), 'Infinity')
        self.assertEqual(format_decimal(None), 'None')

    def test_tool_execution(self):
        mock_session_manager = MagicMock()
        mock_session = MagicMock()

        ctx = TradingContext(
            ticker_symbol="BTC_USD",
            exchange="CRYPTO_DOT_COM",
            starting_balance=Decimal("10000.00"),
            closing_balance=Decimal("0.00"),
            lowest_buy=Decimal("50000.00"),
            highest_buy=Decimal("52000.00"),
            open_positions=[
                MarketData(
                    volume=Decimal("150.50"),
                    high_price=Decimal("52000.00"),
                    low_price=Decimal("50000.00"),
                    close_price=Decimal("51000.00"),
                    timestamp=123456.78
                )
            ],
            position_qty=Decimal("0.1"),
            avg_entry_price=Decimal("51000.00"),
            realized_pnl=Decimal("10.00")
        )
        ctx.available_balance = Decimal("9500.00")

        mock_session.trading_contexts = {1: ctx}
        mock_session_manager.current_session = mock_session

        tool = TradingContextTool(session_manager=mock_session_manager)

        # Execute
        result = tool._run(ticker_symbol="BTC_USD")

        # Verify
        self.assertIn("Trading Context for BTC_USD on CRYPTO_DOT_COM", result)
        self.assertIn("Available Balance: 9500", result)
        self.assertIn("Position Qty: 0.1", result)
        self.assertIn("Avg Entry Price: 51000", result)
        self.assertNotIn("Maker Fee Pct", result)
        self.assertNotIn("Close Price: 52500", result)

    def test_tool_asset_not_found(self):
        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.trading_contexts = {}
        mock_session_manager.current_session = mock_session

        tool = TradingContextTool(session_manager=mock_session_manager)
        result = tool._run(ticker_symbol="ETH_USD")
        self.assertIn("not found", result)


class TestExchangeFeesTool(unittest.TestCase):
    def test_fees_tool_execution(self):
        mock_fees_manager = MagicMock(spec=FeesManager)
        mock_fees = Fees(maker_fee_pct=Decimal("0.1"), taker_fee_pct=Decimal("0.2"))
        mock_fees_manager.get_instrument_fees.return_value = mock_fees

        mock_asset = MagicMock()
        mock_asset.ticker_symbol = "BTC_USD"
        mock_asset.exchange.value = "CRYPTO_DOT_COM"

        tool = ExchangeFeesTool(fees_manager=mock_fees_manager, assets=[mock_asset])
        result = tool._run(ticker_symbol="BTC_USD")

        self.assertIn("Exchange Fees for BTC_USD on CRYPTO_DOT_COM", result)
        self.assertIn("Maker Fee Pct: 0.1%", result)
        self.assertIn("Taker Fee Pct: 0.2%", result)
        mock_fees_manager.get_instrument_fees.assert_called_once_with("CRYPTO_DOT_COM", "BTC_USD")

    def test_fees_tool_asset_not_found(self):
        tool = ExchangeFeesTool(fees_manager=MagicMock(spec=FeesManager), assets=[])
        result = tool._run(ticker_symbol="ETH_USD")
        self.assertIn("not found", result)


class TestMarketStatisticsTool(unittest.TestCase):
    def test_stats_tool_execution(self):
        mock_market_data_manager = MagicMock(spec=MarketDataManager)
        mock_market_data = MarketData(
            volume=Decimal("1200.00"),
            high_price=Decimal("53000.00"),
            low_price=Decimal("50500.00"),
            close_price=Decimal("52500.00"),
            timestamp=123456.90
        )
        mock_market_data_manager.get_market_data.return_value = mock_market_data

        mock_asset = MagicMock()
        mock_asset.ticker_symbol = "BTC_USD"
        mock_asset.exchange.value = "CRYPTO_DOT_COM"

        tool = MarketStatisticsTool(market_data_manager=mock_market_data_manager, assets=[mock_asset])
        result = tool._run(ticker_symbol="BTC_USD")

        self.assertIn("Market Statistics for BTC_USD on CRYPTO_DOT_COM", result)
        self.assertIn("Close Price: 52500", result)
        self.assertIn("Trading Volume: 1200", result)
        mock_market_data_manager.get_market_data.assert_called_once_with(mock_asset)

    def test_stats_tool_asset_not_found(self):
        tool = MarketStatisticsTool(market_data_manager=MagicMock(spec=MarketDataManager), assets=[])
        result = tool._run(ticker_symbol="ETH_USD")
        self.assertIn("not found", result)
