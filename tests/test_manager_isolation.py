import unittest
from unittest.mock import Mock, patch
from api.interfaces.asset import Asset
from api.interfaces.timeframe import Timeframe
from api.interfaces.asset_schedule import AssetSchedule
from database.database_manager import DatabaseManager
from src.trading.protection.protection_manager import ProtectionManager
from src.trading.accounts.account_manager import AccountManager
from src.trading.markets.market_data_manager import MarketDataManager
from src.trading.orders.order_manager import OrderManager
from src.core.interfaces.exchange_rest_client import ExchangeProvidersEnum


class TestManagerIsolation(unittest.TestCase):
    # pylint: disable=protected-access

    def test_protection_manager_isolation(self):
        manager1 = ProtectionManager()
        guard1 = Mock()
        manager1.register_guard(asset_key=1, guard=guard1)

        manager2 = ProtectionManager()

        self.assertNotIn(1, manager2.guards, "ProtectionManager instances should not share guards")
        self.assertEqual(len(manager2.guards), 0, "New ProtectionManager should have empty guards")
        self.assertIn(1, manager1.guards, "Original ProtectionManager should retain its guards")
        self.assertEqual(len(manager1.guards[1]), 1, "Original ProtectionManager should have 1 guard")

    def test_account_manager_isolation(self):
        """Test that AccountManager instances have isolated balances."""
        asset1 = Asset(
            base_ticker_symbol="BTC",
            quote_ticker_symbol="USD",
            decimal_places=2,
            name="Bitcoin",
            exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
            min_quantity=0.0001,
            schedule=AssetSchedule.EVERY_MINUTE,
            candles_timeframe=Timeframe.MIN1
        )

        asset2 = Asset(
            base_ticker_symbol="ETH",
            quote_ticker_symbol="USD",
            decimal_places=2,
            name="Ethereum",
            exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
            min_quantity=0.01,
            schedule=AssetSchedule.EVERY_MINUTE,
            candles_timeframe=Timeframe.MIN1
        )

        ws_manager1 = Mock()
        rest_manager1 = Mock()
        manager1 = AccountManager([asset1], rest_manager1, ws_manager1)
        manager1.balances = {"provider1": {"USD": Mock(available_balance=1000)}}

        ws_manager2 = Mock()
        rest_manager2 = Mock()
        manager2 = AccountManager([asset2], rest_manager2, ws_manager2)

        self.assertEqual(len(manager2.balances), 0, "New AccountManager should have empty balances")
        self.assertIn("provider1", manager1.balances, "Original AccountManager should retain balances")

    def test_market_data_manager_isolation(self):
        """Test that MarketDataManager instances have isolated market data caches."""
        asset1 = Asset(
            base_ticker_symbol="BTC",
            quote_ticker_symbol="USD",
            decimal_places=2,
            name="Bitcoin",
            exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
            min_quantity=0.0001,
            schedule=AssetSchedule.EVERY_MINUTE,
            candles_timeframe=Timeframe.MIN1
        )

        asset2 = Asset(
            base_ticker_symbol="ETH",
            quote_ticker_symbol="USD",
            decimal_places=2,
            name="Ethereum",
            exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
            min_quantity=0.01,
            schedule=AssetSchedule.EVERY_MINUTE,
            candles_timeframe=Timeframe.MIN1
        )

        ws_manager1 = Mock()
        rest_manager1 = Mock()
        manager1 = MarketDataManager(rest_manager1, ws_manager1)
        with patch.object(manager1, 'get_candles', return_value=[]):
            manager1.initialize([asset1])
        manager1._market_data = {asset1.key: Mock(close_price="50000")}

        ws_manager2 = Mock()
        rest_manager2 = Mock()
        manager2 = MarketDataManager(rest_manager2, ws_manager2)
        with patch.object(manager2, 'get_candles', return_value=[]):
            manager2.initialize([asset2])

        self.assertNotIn(asset1.key, manager2._market_data, "New MarketDataManager should not have asset1 data")
        self.assertIn(asset2.key, manager2._market_data, "New MarketDataManager should have asset2 initialized")
        self.assertIn(asset1.key, manager1._market_data, "Original MarketDataManager should retain data")

    def test_order_manager_isolation(self):
        db_manager1 = Mock(spec=DatabaseManager)
        journal1 = Mock()
        ws_manager1 = Mock()
        rest_manager1 = Mock()
        manager1 = OrderManager(db_manager1, journal1, rest_manager1, ws_manager1)

        db_manager2 = Mock(spec=DatabaseManager)
        journal2 = Mock()
        ws_manager2 = Mock()
        rest_manager2 = Mock()
        manager2 = OrderManager(db_manager2, journal2, rest_manager2, ws_manager2)

        self.assertNotEqual(manager1._database_manager, manager2._database_manager)
        self.assertNotEqual(manager1._trading_journal, manager2._trading_journal)
