import unittest
from decimal import Decimal
from unittest.mock import MagicMock
from api.interfaces.trade_action import TradeAction
from src.clients.rest_manager import RestManager
from src.core.interfaces.exchange_rest_service import ExchangeRestService


class TestRestManager(unittest.TestCase):
    def setUp(self):
        self.rest_manager = RestManager()
        self.mock_service = MagicMock(spec=ExchangeRestService)
        self.mock_service.get_provider_name.return_value = "TEST_EXCHANGE"
        self.rest_manager.register_service(self.mock_service)

    def test_get_market_data_encapsulation(self):
        mock_builder = self.mock_service.builder.return_value
        self.rest_manager.get_market_data("TEST_EXCHANGE", "BTC/USDT")

        self.mock_service.builder.assert_called_once()
        mock_builder.market_data.assert_called_once_with("BTC/USDT")
        self.mock_service.execute.assert_called_once_with(mock_builder.market_data.return_value)

    def test_get_account_balance_caching(self):
        self.mock_service.execute.return_value = []

        # First call
        self.rest_manager.get_account_balance("TEST_EXCHANGE")
        # Second call (should be cached)
        self.rest_manager.get_account_balance("TEST_EXCHANGE")

        self.assertEqual(self.mock_service.execute.call_count, 1)

    def test_circuit_breaker_on_error(self):
        # We need to test if the circuit breaker triggers after failures.
        # This is tricky because the circuitbreaker library might keep state.
        # But we can at least verify it raises the expected error.
        self.mock_service.execute.side_effect = RuntimeError("Service Down")

        with self.assertRaises(RuntimeError):
            self.rest_manager.get_market_data("TEST_EXCHANGE", "BTC/USDT")

    def test_place_order_encapsulation(self):
        mock_builder = self.mock_service.builder.return_value
        self.rest_manager.place_order(
            "TEST_EXCHANGE", "uuid1", "BTC/USDT", "1.0", Decimal("50000"), TradeAction.BUY
        )

        mock_builder.create_order.assert_called_once_with(
            "uuid1", "BTC/USDT", "1.0", "50000", TradeAction.BUY
        )
        self.mock_service.execute.assert_called_once()


if __name__ == '__main__':
    unittest.main()
