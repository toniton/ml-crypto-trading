import unittest
from unittest.mock import MagicMock

from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.subscription_data import SubscriptionData, SubscriptionVisibility
from src.simulation.simulated_websocket_manager import SimulatedWebSocketManager


class TestSimulatedWebSocketManager(unittest.TestCase):
    def setUp(self):
        self.manager = SimulatedWebSocketManager()
        self.mock_service = MagicMock(spec=ExchangeWebSocketService)
        self.mock_service.get_provider_name.return_value = "TEST_EXCHANGE"
        self.manager.register_service(self.mock_service)

    def test_subscribe_public_calls_super(self):
        mock_builder = MagicMock(spec=ExchangeWebSocketBuilder)
        mock_sub_data = MagicMock(spec=SubscriptionData)
        mock_sub_data.visibility = SubscriptionVisibility.PUBLIC
        mock_builder.get_subscription_data.return_value = mock_sub_data

        callback = MagicMock()

        # We need to mock the super()._subscribe call or verify it reached the service
        self.manager._subscribe("test_key", self.mock_service, mock_builder, callback)

        self.mock_service.subscribe.assert_called_once_with(mock_builder)
        self.assertEqual(self.manager._subscriptions["TEST_EXCHANGE"]["test_key"], (mock_builder, callback))

    def test_subscribe_private_skips_service_subscribe(self):
        mock_builder = MagicMock(spec=ExchangeWebSocketBuilder)
        mock_sub_data = MagicMock(spec=SubscriptionData)
        mock_sub_data.visibility = SubscriptionVisibility.PRIVATE
        mock_builder.get_subscription_data.return_value = mock_sub_data

        callback = MagicMock()

        self.manager._subscribe("test_key", self.mock_service, mock_builder, callback)

        # Should NOT call service.subscribe
        self.mock_service.subscribe.assert_not_called()
        # But SHOULD still register in internal subscriptions
        self.assertEqual(self.manager._subscriptions["TEST_EXCHANGE"]["test_key"], (mock_builder, callback))
