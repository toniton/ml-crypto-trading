import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.account_balance import AccountBalance
from src.llm.tools.account_balance_tool import AccountBalanceTool
from src.trading.accounts.account_manager import AccountManager


class TestAccountBalanceTool(unittest.TestCase):
    def _asset(self):
        asset = MagicMock()
        asset.ticker_symbol = "BTC_USD"
        asset.exchange.value = "CRYPTO_DOT_COM"
        return asset

    def test_formats_balances(self):
        account_manager = MagicMock(spec=AccountManager)
        account_manager.get_base_balance.return_value = AccountBalance("BTC", Decimal("1.5"))
        account_manager.get_quote_balance.return_value = AccountBalance("USD", Decimal("9500"))
        tool = AccountBalanceTool(account_manager=account_manager, assets=[self._asset()])
        result = tool._run("BTC_USD")
        self.assertIn("Account Balance for BTC_USD on CRYPTO_DOT_COM", result)
        self.assertIn("Base (BTC): 1.5", result)
        self.assertIn("Quote (USD): 9500", result)

    def test_asset_not_found(self):
        tool = AccountBalanceTool(account_manager=MagicMock(spec=AccountManager), assets=[])
        self.assertIn("not found", tool._run("ETH_USD"))

    def test_error_propagated(self):
        account_manager = MagicMock(spec=AccountManager)
        account_manager.get_base_balance.side_effect = RuntimeError("boom")
        tool = AccountBalanceTool(account_manager=account_manager, assets=[self._asset()])
        self.assertIn("boom", tool._run("BTC_USD"))
