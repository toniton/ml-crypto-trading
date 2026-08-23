import unittest
from unittest.mock import MagicMock

from src.llm.tools.session_summary_tool import SessionSummaryTool
from src.trading.session.session_manager import SessionManager


class TestSessionSummaryTool(unittest.TestCase):
    def _summary(self):
        return {
            "session_id": "sess-1",
            "commit_hash": "abc",
            "is_running": True,
            "duration": 12.0,
            "assets": 1,
            "contexts": {
                1: {
                    "ticker_symbol": "BTC_USD",
                    "exchange": "CRYPTO_DOT_COM",
                    "starting_balance": 10000,
                    "available_balance": 9500,
                    "closing_balance": 0,
                    "buy_count": 2,
                }
            },
        }

    def test_formats_summary(self):
        session_manager = MagicMock(spec=SessionManager)
        session_manager.current_session = MagicMock()
        session_manager.get_session_summary.return_value = self._summary()
        tool = SessionSummaryTool(session_manager=session_manager)
        result = tool._run()
        self.assertIn("Session summary for sess-1", result)
        self.assertIn("BTC_USD", result)
        self.assertIn("buys=2", result)

    def test_no_active_session(self):
        session_manager = MagicMock(spec=SessionManager)
        session_manager.current_session = None
        tool = SessionSummaryTool(session_manager=session_manager)
        self.assertIn("No active trading session", tool._run())
