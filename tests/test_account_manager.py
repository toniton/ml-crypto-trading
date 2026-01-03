import unittest
from unittest.mock import MagicMock, patch
from api.interfaces.account_balance import AccountBalance
from api.interfaces.trading_context import TradingContext
from src.trading.accounts.account_manager import AccountManager
from src.trading.context.trading_context_manager import TradingContextManager


class TestAccountManager(unittest.TestCase):
    def setUp(self):
        self.mock_asset = MagicMock()
        self.mock_asset.exchange.value = "BINANCE"
        self.mock_asset.quote_ticker_symbol = "USDT"
        self.mock_asset.key = "BTC/USDT"
        self.assets = [self.mock_asset]
        self.account_manager = AccountManager(self.assets)

    def test_init_websocket(self):
        mock_websocket = MagicMock()
        self.account_manager.websockets = {"BINANCE": mock_websocket}

        self.account_manager.init_websocket()

        mock_websocket.subscribe_balance.assert_called_once()
        _, kwargs = mock_websocket.subscribe_balance.call_args
        self.assertTrue(callable(kwargs.get('callback')), "Callback should be passed")

    def test_init_account_balances_success(self):
        mock_context_manager = MagicMock(spec=TradingContextManager)
        mock_balance = AccountBalance(currency="USDT", available_balance=1000.0)

        with patch.object(self.account_manager, 'get_balance', return_value=mock_balance) as mock_get_balance:
            self.account_manager.init_account_balances(mock_context_manager)

            mock_get_balance.assert_called_with("USDT", "BINANCE")
            mock_context_manager.register_trading_context.assert_called_once()
            call_args = mock_context_manager.register_trading_context.call_args
            self.assertEqual(call_args[0][0], "BTC/USDT")
            self.assertIsInstance(call_args[0][1], TradingContext)
            self.assertEqual(call_args[0][1].starting_balance, 1000.0)

    def test_init_account_balances_failure(self):
        mock_context_manager = MagicMock(spec=TradingContextManager)

        with patch.object(self.account_manager, 'get_balance', side_effect=Exception("API Error")):
            with self.assertLogs(self.account_manager.app_logger.name, level='ERROR') as log:
                self.account_manager.init_account_balances(mock_context_manager)
                self.assertIn("Unable to initialize account balance", log.output[0])

            mock_context_manager.register_trading_context.assert_not_called()

    def test_get_balance_cached(self):
        provider_name = "BINANCE"
        currency = "USDT"
        expected_balance = AccountBalance(currency="USDT", available_balance=500.0)
        self.account_manager.balances = {provider_name: {currency: expected_balance}}

        balance = self.account_manager.get_balance(currency, provider_name)

        self.assertEqual(balance, expected_balance)

    def test_get_balance_fetch_success(self):
        provider_name = "BINANCE"
        currency = "USDT"
        expected_balance = AccountBalance(currency="USDT", available_balance=500.0)

        mock_provider = MagicMock()
        mock_provider.get_account_balance.return_value = [expected_balance]

        with patch.object(self.account_manager, 'get_client', return_value=mock_provider):
            balance = self.account_manager.get_balance(currency, provider_name)

            self.assertEqual(balance, expected_balance)
            self.assertIn(provider_name, self.account_manager.balances)
            self.assertIn(currency, self.account_manager.balances[provider_name])
            self.assertEqual(self.account_manager.balances[provider_name][currency], expected_balance)

    def test_get_balance_fetch_empty_returns_zero_balance(self):
        provider_name = "BINANCE"
        currency = "USDT"

        mock_provider = MagicMock()
        mock_provider.get_account_balance.return_value = []

        with patch.object(self.account_manager, 'get_client', return_value=mock_provider):
            balance = self.account_manager.get_balance(currency, provider_name)

            self.assertEqual(balance.currency, "USDT")
            self.assertEqual(balance.available_balance, 0)

    def test_cache_balances_updates_existing(self):
        provider_name = "BINANCE"
        initial_balance = AccountBalance(currency="USDT", available_balance=100.0)
        new_balance = AccountBalance(currency="USDT", available_balance=200.0)

        self.account_manager.balances = {provider_name: {"USDT": initial_balance}}

        self.account_manager._cache_balances(provider_name, [new_balance])

        self.assertEqual(self.account_manager.balances[provider_name]["USDT"], new_balance)

    def test_cache_balances_adds_new_provider(self):
        provider_name = "KRAKEN"
        new_balance = AccountBalance(currency="EUR", available_balance=500.0)

        self.account_manager._cache_balances(provider_name, [new_balance])
        self.assertIn(provider_name, self.account_manager.balances)
        self.assertEqual(self.account_manager.balances[provider_name]["EUR"], new_balance)
