import unittest
from unittest.mock import MagicMock, patch
from src.clients.websocket_manager import WebSocketManager
from src.core.interfaces.subscription_data import SubscriptionVisibility


class TestWebSocketManagerCloseHandling(unittest.TestCase):
    def setUp(self):
        # Patch the property in the class capable of it, or mock the logger retrieval
        self.patcher = patch('src.core.logging.application_logging_mixin.ApplicationLoggingMixin.app_logger')
        self.mock_logger = self.patcher.start()

        self.manager = WebSocketManager()

    def tearDown(self):
        self.patcher.stop()

    def test_handle_close_logs_and_clears_connection(self):
        # Setup
        exchange = "TEST_EXCHANGE"
        visibility = SubscriptionVisibility.PUBLIC
        conn_id = f"{exchange}-{visibility.value}"

        # Manually populate connections to simulate active connection
        mock_conn = MagicMock()
        self.manager._connections[exchange] = {visibility: mock_conn}

        # Execute
        self.manager._handle_close(exchange, visibility, 1000, "Normal Closure")

        # Verify
        self.manager.app_logger.info.assert_any_call(
            f"WebSocket closed for {conn_id}. Code: 1000, Msg: Normal Closure")

        # Should have removed from connections
        self.assertNotIn(visibility, self.manager._connections[exchange])
