import unittest
from unittest.mock import MagicMock

from src.agent.configuration.configuration_service import ConfigurationService
from src.llm.tools.configuration_tool import ConfigurationTool


class TestConfigurationTool(unittest.TestCase):
    def _raw_config(self):
        return {
            "assets": [
                {
                    "name": "Bitcoin",
                    "base_ticker_symbol": "BTC",
                    "quote_ticker_symbol": "USD",
                    "exchange": "CRYPTO_DOT_COM",
                    "min_quantity": 0.00005,
                    "consensus": {"buy": 1.3, "sell": 0.5},
                }
            ]
        }

    def test_formats_asset_configuration(self):
        service = MagicMock(spec=ConfigurationService)
        service.load_raw_config.return_value = self._raw_config()
        tool = ConfigurationTool(configuration_service=service)
        result = tool._run("BTC_USD")
        self.assertIn("Configuration for BTC_USD", result)
        self.assertIn("min_quantity", result)

    def test_asset_not_found(self):
        service = MagicMock(spec=ConfigurationService)
        service.load_raw_config.return_value = self._raw_config()
        tool = ConfigurationTool(configuration_service=service)
        result = tool._run("ETH_USD")
        self.assertIn("not found", result)
        self.assertIn("BTC_USD", result)

    def test_load_error(self):
        service = MagicMock(spec=ConfigurationService)
        service.load_raw_config.side_effect = RuntimeError("boom")
        tool = ConfigurationTool(configuration_service=service)
        self.assertIn("boom", tool._run("BTC_USD"))
