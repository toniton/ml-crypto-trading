import unittest
from unittest.mock import MagicMock

from src.llm.tools.trading_context_tool import TradingContextTool


class TestTradingContextTool(unittest.TestCase):
    def test_tool_execution(self):
        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.ticker_symbol = "BTC_USD"
        mock_ctx.__str__.return_value = "BTC_USD context"

        mock_session.trading_contexts = {1: mock_ctx}
        mock_session_manager.current_session = mock_session

        tool = TradingContextTool(session_manager=mock_session_manager)

        # Execute
        result = tool._run(ticker_symbol="BTC_USD")

        # Verify
        self.assertEqual(result, "BTC_USD context")

    def test_tool_asset_not_found(self):
        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.trading_contexts = {}
        mock_session_manager.current_session = mock_session

        tool = TradingContextTool(session_manager=mock_session_manager)
        result = tool._run(ticker_symbol="ETH_USD")
        self.assertIn("not found", result)
