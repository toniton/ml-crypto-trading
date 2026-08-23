import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.trading_context import TradingContext
from src.llm.tools.position_tool import PositionTool
from src.trading.session.session_manager import SessionManager


class TestPositionTool(unittest.TestCase):
    def _context(self):
        ctx = TradingContext(
            ticker_symbol="BTC_USD",
            exchange="CRYPTO_DOT_COM",
            starting_balance=Decimal("10000"),
            position_qty=Decimal("0.1"),
            avg_entry_price=Decimal("51000"),
            realized_pnl=Decimal("10"),
        )
        return ctx

    def test_formats_position(self):
        session = MagicMock()
        session.trading_contexts = {1: self._context()}
        session_manager = MagicMock(spec=SessionManager)
        session_manager.current_session = session

        tool = PositionTool(session_manager=session_manager, assets=[])
        result = tool._run("BTC_USD")
        self.assertIn("Position for BTC_USD on CRYPTO_DOT_COM", result)
        self.assertIn("Position Qty: 0.1", result)
        self.assertIn("Avg Entry Price: 51000", result)

    def test_no_active_session(self):
        session_manager = MagicMock(spec=SessionManager)
        session_manager.current_session = None
        tool = PositionTool(session_manager=session_manager, assets=[])
        self.assertIn("No active trading session", tool._run("BTC_USD"))

    def test_asset_not_found(self):
        session = MagicMock()
        session.trading_contexts = {}
        session_manager = MagicMock(spec=SessionManager)
        session_manager.current_session = session
        tool = PositionTool(session_manager=session_manager, assets=[])
        self.assertIn("not found", tool._run("BTC_USD"))
