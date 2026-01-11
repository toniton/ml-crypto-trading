import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from api.interfaces.account_balance import AccountBalance
from src.trading.accounts.account_manager import AccountManager
from src.trading.session.session_manager import SessionManager


class TestAccountManager(unittest.TestCase):
    def setUp(self):
        self.mock_asset = MagicMock()
        self.mock_asset.exchange.value = "BINANCE"
        self.mock_asset.quote_ticker_symbol = "USDT"
        self.mock_asset.key = "BTC/USDT"
        self.assets = [self.mock_asset]
        self.mock_websocket_manager = MagicMock()
        self.account_manager = AccountManager(self.assets, self.mock_websocket_manager)

    def test_init_websocket(self):
        mock_websocket = MagicMock()
        self.account_manager.websockets = {"BINANCE": mock_websocket}
        self.account_manager.init_websocket()

        self.mock_websocket_manager.subscribe_account_balance.assert_called_once()
        _, kwargs = self.mock_websocket_manager.subscribe_account_balance.call_args
        self.assertTrue(callable(kwargs.get('callback')), "Callback should be passed")

    def test_init_account_balances_success(self):
        mock_session_manager = MagicMock(spec=SessionManager)
        mock_balance = AccountBalance(currency="USDT", available_balance=Decimal("1000.0"))

        with patch.object(self.account_manager, 'get_quote_balance', return_value=mock_balance) as mock_get_balance:
            self.account_manager.init_account_balances(mock_session_manager)

            mock_get_balance.assert_called_with(self.mock_asset, "BINANCE")
            mock_session_manager.init_asset_balance.assert_called_once()
            call_args = mock_session_manager.init_asset_balance.call_args
            self.assertEqual(self.mock_asset, call_args[0][0])
            self.assertEqual(Decimal("1000.0"), call_args[0][1])

    def test_init_account_balances_failure(self):
        mock_session_manager = MagicMock(spec=SessionManager)

        with patch.object(self.account_manager, 'get_quote_balance', side_effect=Exception("API Error")):
            with self.assertLogs(self.account_manager.app_logger.name, level='ERROR') as log:
                self.account_manager.init_account_balances(mock_session_manager)
                self.assertIn("Unable to initialize account balance", log.output[0])

            mock_session_manager.init_asset_balance.assert_not_called()

    def test_get_balance_cached(self):
        provider_name = "BINANCE"
        currency = "USDT"
        expected_balance = AccountBalance(currency="USDT", available_balance=Decimal("500.0"))
        mock_rest_client = MagicMock()
        self.account_manager.rest_clients = {"BINANCE": mock_rest_client}
        self.account_manager.balances = {provider_name: {currency: expected_balance}}

        balance = self.account_manager.get_quote_balance(self.mock_asset, provider_name)

        self.assertEqual(balance, expected_balance)

    def test_get_balance_fetch_success(self):
        provider_name = "BINANCE"
        currency = "USDT"
        expected_balance = AccountBalance(currency="USDT", available_balance=Decimal("500.0"))

        mock_provider = MagicMock()
        mock_provider.get_account_balance.return_value = [expected_balance]

        with patch.object(self.account_manager, 'get_client', return_value=mock_provider):
            balance = self.account_manager.get_quote_balance(self.mock_asset, provider_name)

            self.assertEqual(balance, expected_balance)
            self.assertIn(provider_name, self.account_manager.balances)
            self.assertIn(currency, self.account_manager.balances[provider_name])
            self.assertEqual(self.account_manager.balances[provider_name][currency], expected_balance)

    def test_get_balance_fetch_empty_returns_zero_balance(self):
        provider_name = "BINANCE"

        mock_provider = MagicMock()
        mock_provider.get_account_balance.return_value = []

        with patch.object(self.account_manager, 'get_client', return_value=mock_provider):
            balance = self.account_manager.get_quote_balance(self.mock_asset, provider_name)

            self.assertEqual(balance.currency, "USDT")
            self.assertEqual(balance.available_balance, Decimal("0"))

    def test_cache_balances_updates_existing(self):
        provider_name = "BINANCE"
        initial_balance = AccountBalance(currency="USDT", available_balance=Decimal("100.0"))
        new_balance = AccountBalance(currency="USDT", available_balance=Decimal("200.0"))

        self.account_manager.balances = {provider_name: {"USDT": initial_balance}}

        self.account_manager._cache_balances(provider_name, [new_balance])

        self.assertEqual(self.account_manager.balances[provider_name]["USDT"], new_balance)

    def test_cache_balances_adds_new_provider(self):
        provider_name = "KRAKEN"
        new_balance = AccountBalance(currency="EUR", available_balance=Decimal("500.0"))

        self.account_manager._cache_balances(provider_name, [new_balance])
        self.assertIn(provider_name, self.account_manager.balances)
        self.assertEqual(self.account_manager.balances[provider_name]["EUR"], new_balance)
