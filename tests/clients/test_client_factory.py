from unittest.mock import MagicMock

from src.clients.client_factory import ClientFactory
from src.clients.rest_manager import RestManager
from src.clients.websocket_manager import WebSocketManager
from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.subscription_data import SubscriptionData, SubscriptionVisibility
from src.core.simulation.simulated_rest_manager import SimulatedRestManager
from src.core.simulation.simulated_websocket_manager import SimulatedWebSocketManager


def test_client_factory_real_managers():
    rest_manager = ClientFactory.create_rest_manager(is_simulated=False)
    websocket_manager = ClientFactory.create_websocket_manager(is_simulated=False)

    assert isinstance(rest_manager, RestManager)
    assert not isinstance(rest_manager, SimulatedRestManager)
    assert isinstance(websocket_manager, WebSocketManager)
    assert not isinstance(websocket_manager, SimulatedWebSocketManager)


def test_client_factory_simulated_managers():
    rest_manager = ClientFactory.create_rest_manager(is_simulated=True)
    websocket_manager = ClientFactory.create_websocket_manager(is_simulated=True)

    assert isinstance(rest_manager, SimulatedRestManager)
    assert isinstance(websocket_manager, SimulatedWebSocketManager)


def test_simulated_websocket_manager_skips_private(mocker):
    # Mock the logger before instantiating the manager
    mock_logger = MagicMock()
    mocker.patch('src.core.logging.factory.LoggingFactory.get_application_logger', return_value=mock_logger)

    swm = SimulatedWebSocketManager()
    service = MagicMock(spec=ExchangeWebSocketService)
    service.get_provider_name.return_value = "test_exchange"
    swm.get_service = MagicMock(return_value=service)

    # Register service to initialize dictionaries
    swm.register_service(service)

    # Test _subscribe for private
    callback = MagicMock()
    builder = MagicMock(spec=ExchangeWebSocketBuilder)
    sub_data = MagicMock(spec=SubscriptionData)
    sub_data.visibility = SubscriptionVisibility.PRIVATE
    builder.get_subscription_data.return_value = sub_data

    swm._subscribe("key1", service, builder, callback)
    mock_logger.info.assert_any_call("Simulated mode: Skipping private subscription for key1 on test_exchange")

    # Verify subscription was registered despite skip (to maintain consistency)
    assert "test_exchange" in swm._subscriptions
    assert "key1" in swm._subscriptions["test_exchange"]
