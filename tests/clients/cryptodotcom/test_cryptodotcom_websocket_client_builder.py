import unittest
from api.interfaces.timeframe import Timeframe
from src.clients.cryptodotcom.cryptodotcom_websocket_builder import CryptoDotComWebSocketBuilder
from src.core.interfaces.subscription_data import SubscriptionVisibility


class TestCryptoDotComWebSocketClient(unittest.TestCase):
    def setUp(self):
        self.client = CryptoDotComWebSocketBuilder()

    def test_market_data_builder(self):
        self.client.market_data("BTC_USDT")
        sub_data = self.client.get_subscription_data()

        self.assertEqual(sub_data.visibility, SubscriptionVisibility.PUBLIC)
        self.assertIn("ticker.BTC_USDT", sub_data.payload["params"]["channels"])
        self.assertIsInstance(sub_data.payload["id"], int)

    def test_candles_builder(self):
        self.client.candles("BTC_USDT", Timeframe.MIN1)
        sub_data = self.client.get_subscription_data()

        self.assertEqual(sub_data.visibility, SubscriptionVisibility.PUBLIC)
        self.assertIn("candlestick.1m.BTC_USDT", sub_data.payload["params"]["channels"])
        self.assertIsInstance(sub_data.payload["id"], int)

    def test_account_balance_builder(self):
        self.client.account_balance()
        sub_data = self.client.get_subscription_data()

        self.assertEqual(sub_data.visibility, SubscriptionVisibility.PRIVATE)
        self.assertIn("user.balance", sub_data.payload["params"]["channels"])
        self.assertIsInstance(sub_data.payload["id"], int)

    def test_order_update_builder(self):
        self.client.order_update("BTC_USDT")
        sub_data = self.client.get_subscription_data()

        self.assertEqual(sub_data.visibility, SubscriptionVisibility.PRIVATE)
        self.assertIn("user.order.BTC_USDT", sub_data.payload["params"]["channels"])
        self.assertIsInstance(sub_data.payload["id"], int)

    def test_builder_chaining(self):
        # Chaining should return self
        result = self.client.market_data("ETH_USDT")
        self.assertIs(result, self.client)

        sub_data = self.client.get_subscription_data()
        self.assertIn("ticker.ETH_USDT", sub_data.payload["params"]["channels"])

    def test_get_unsubscribe_payload(self):
        self.client.market_data("BTC_USDT")
        sub_data = self.client.get_subscription_data()

        unsub_payload = self.client.get_unsubscribe_payload(sub_data.payload)
        self.assertEqual(unsub_payload["method"], "unsubscribe")
        self.assertEqual(unsub_payload["params"], sub_data.payload["params"])
        self.assertNotEqual(unsub_payload["id"], sub_data.payload["id"])
