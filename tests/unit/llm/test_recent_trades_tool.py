import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.core.interfaces.trading_journal import TradingJournal
from src.llm.tools.recent_trades_tool import RecentTradesTool


class TestRecentTradesTool(unittest.TestCase):
    def _asset(self):
        asset = MagicMock()
        asset.ticker_symbol = "BTC_USD"
        return asset

    def _order(self, uuid="1", qty="0.1", price="51000"):
        return Order(
            uuid=uuid,
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal(price),
            quantity=qty,
            trade_action=TradeAction.BUY,
            created_time=123.0,
            status=OrderStatus.COMPLETED,
        )

    def test_formats_recent_trades(self):
        journal = MagicMock(spec=TradingJournal)
        journal.entries.return_value = [self._order(), self._order(uuid="2", qty="0.2")]
        tool = RecentTradesTool(trading_journal=journal, assets=[self._asset()])
        result = tool._run("BTC_USD", limit=10)
        self.assertIn("Recent trades for BTC_USD", result)
        self.assertIn("BUY", result)
        self.assertIn("qty=0.1", result)
        journal.entries.assert_called_once_with("BTC_USD")

    def test_no_trades(self):
        journal = MagicMock(spec=TradingJournal)
        journal.entries.return_value = []
        tool = RecentTradesTool(trading_journal=journal, assets=[self._asset()])
        self.assertIn("No completed trades", tool._run("BTC_USD"))

    def test_asset_not_found(self):
        tool = RecentTradesTool(trading_journal=MagicMock(spec=TradingJournal), assets=[])
        self.assertIn("not found", tool._run("ETH_USD"))
