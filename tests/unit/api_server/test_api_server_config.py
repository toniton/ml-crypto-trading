import os
import sys
import unittest
from unittest.mock import MagicMock

from src.configuration.application_config import ApplicationConfig
from src.server.server import ApiServer
from src.events.message_event_bus import MessageEventBus
from src.recorder.market_data_store import MarketDataStore


class TestApiServerConfig(unittest.TestCase):
    def setUp(self):
        self.orig_environ = os.environ.copy()
        self.orig_argv = sys.argv.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_environ)
        sys.argv = self.orig_argv.copy()

    def test_default_host_and_port(self):
        sys.argv = ["pytest", "--assets-conf=config.yaml"]
        config = ApplicationConfig()
        self.assertEqual(config.api_host, "0.0.0.0")
        self.assertEqual(config.api_port, 8000)

    def test_port_and_host_from_environment(self):
        sys.argv = ["pytest", "--assets-conf=config.yaml"]
        os.environ["PORT"] = "80"
        os.environ["HOST"] = "0.0.0.0"
        config = ApplicationConfig()
        self.assertEqual(config.api_port, 80)
        self.assertEqual(config.api_host, "0.0.0.0")

    def test_api_port_and_api_host_from_environment(self):
        sys.argv = ["pytest", "--assets-conf=config.yaml"]
        os.environ["API_PORT"] = "9000"
        os.environ["API_HOST"] = "127.0.0.1"
        config = ApplicationConfig()
        self.assertEqual(config.api_port, 9000)
        self.assertEqual(config.api_host, "127.0.0.1")

    def test_port_and_host_from_cli_flags(self):
        sys.argv = ["pytest", "--assets-conf=config.yaml", "--port=8080", "--host=0.0.0.0"]
        config = ApplicationConfig()
        self.assertEqual(config.api_port, 8080)
        self.assertEqual(config.api_host, "0.0.0.0")

    def test_api_port_and_api_host_from_cli_flags(self):
        sys.argv = ["pytest", "--assets-conf=config.yaml", "--api-port=3000", "--api-host=127.0.0.1"]
        config = ApplicationConfig()
        self.assertEqual(config.api_port, 3000)
        self.assertEqual(config.api_host, "127.0.0.1")

    def test_api_server_default_host_and_port(self):
        agent = MagicMock()
        event_bus = MessageEventBus()
        db_manager = MagicMock()
        market_data_store = MarketDataStore()
        vcs = MagicMock()

        server = ApiServer(
            agent=agent,
            event_bus=event_bus,
            db_manager=db_manager,
            market_data_store=market_data_store,
            vcs=vcs,
        )
        self.assertEqual(server.host, "0.0.0.0")
        self.assertEqual(server.port, 8000)


if __name__ == "__main__":
    unittest.main()
