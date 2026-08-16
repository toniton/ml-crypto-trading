import unittest
from unittest.mock import MagicMock

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.trading_oracle import TradingOracle


class TestTradingOracle(unittest.TestCase):
    def test_generate_report(self):
        mock_llm = MagicMock()
        mock_tool = MagicMock()
        mock_llm.generate.return_value = "Report Content"
        oracle = TradingOracle(llm=mock_llm)
        oracle.register_tool(mock_tool)

        asset = Asset(
            base_ticker_symbol="BTC",
            quote_ticker_symbol="USD",
            quote_decimals=2,
            name="Bitcoin",
            exchange=ExchangeProvidersEnum.BACKTEST,
            min_quantity=0.001,
            quantity_decimals=3,
            schedule=AssetSchedule.EVERY_MINUTE,
            candles_timeframe=Timeframe.MIN1
        )
        report = oracle.generate_report([asset])

        self.assertEqual(report, "Report Content")
        mock_llm.generate.assert_called_once()
        mock_llm.bind_tools.assert_called_once()

    def test_register_tools(self):
        mock_llm = MagicMock()
        mock_tool_1 = MagicMock()
        mock_tool_2 = MagicMock()

        oracle = TradingOracle(llm=mock_llm)
        oracle.register_tools([mock_tool_1, mock_tool_2])

        mock_llm.bind_tools.assert_called_once_with([mock_tool_1, mock_tool_2])
