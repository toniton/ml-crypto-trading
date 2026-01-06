import unittest
from unittest.mock import MagicMock, patch
from src.core.managers.websocket_manager import WebSocketManager
from src.core.interfaces.subscription_data import SubscriptionData, SubscriptionVisibility


class TestWebSocketManagerCloseHandling(unittest.TestCase):
    def setUp(self):
        self.mock_get_url = MagicMock(return_value="ws://test.url")
        # Patch the property in the class capable of it, or mock the logger retrieval
        self.patcher = patch('src.core.logging.application_logging_mixin.ApplicationLoggingMixin.app_logger')
        self.mock_logger = self.patcher.start()

        self.manager = WebSocketManager(
            provider_name="TEST_PROVIDER",
            get_websocket_url=self.mock_get_url
        )

    def tearDown(self):
        self.patcher.stop()

        # We need to mock WebSocketApp class itself so when it's instantiated we get a mock
        # But since we are importing it inside the module, we might need to patch it in the file.
        # However, it's imported as 'from websocket import WebSocketApp'
        # So we can patch src.core.managers.websocket_manager.WebSocketApp

    def test_handle_close_1000_reconnects(self):
        # Setup
        event_key = "test_key"
        sub_data = SubscriptionData(
            visibility=SubscriptionVisibility.PUBLIC,
            subscribe_payload={"op": "sub"},
            unsubscribe_payload={"op": "unsub"}
        )
        callback = MagicMock()

        # Manually populate subscriptions to simulate active sub
        self.manager.subscriptions[event_key] = (sub_data, callback)
        # Manually populate connections to simulate active connection
        self.manager.connections[event_key] = MagicMock()

        # Mock subscribe method to verify it's called
        self.manager.subscribe = MagicMock()

        # Execute
        self.manager._handle_close(event_key, 1000, "Normal Closure")

        # Verify
        self.manager.app_logger.info.assert_any_call(
            f"WebSocket closed normally (1000) for {event_key}, reconnecting...")
        # Should call subscribe again with original data
        self.manager.subscribe.assert_called_once_with(event_key, sub_data, callback)
        # Should have removed from connections (subscribe adds it back, but logically we check delete)
        # Since we mocked subscribe, it won't add it back, so we can check if it was deleted
        self.assertNotIn(event_key, self.manager.connections)

    def test_handle_close_other_code_does_not_reconnect(self):
        # Setup
        event_key = "test_key_error"
        sub_data = SubscriptionData(
            visibility=SubscriptionVisibility.PUBLIC,
            subscribe_payload={"op": "sub"},
            unsubscribe_payload={"op": "unsub"}
        )
        callback = MagicMock()

        self.manager.subscriptions[event_key] = (sub_data, callback)
        self.manager.connections[event_key] = MagicMock()

        self.manager.subscribe = MagicMock()

        # Execute
        self.manager._handle_close(event_key, 1006, "Abnormal Closure")

        # Verify
        self.manager.app_logger.warning.assert_called()
        self.manager.subscribe.assert_not_called()
        self.assertNotIn(event_key, self.manager.connections)
        self.assertNotIn(event_key, self.manager.subscriptions)
