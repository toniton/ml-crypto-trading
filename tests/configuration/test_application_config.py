import sys
import unittest
from unittest.mock import patch
from src.configuration.application_config import ApplicationConfig


class TestApplicationConfig(unittest.TestCase):
    def test_backtest_source_alias(self):
        test_path = "/path/to/custom/history"

        with patch.object(sys, "argv", ["app", "--backtest-source", test_path, "--assets-conf", "dummy.yaml"]):
            config = ApplicationConfig()
            assert config.historical_data_dir_path == test_path

    def test_validation_error_when_missing_source(self):
        with self.assertRaises(SystemExit) as cm:
            ApplicationConfig(backtest_mode=True)
        self.assertEqual(cm.exception.code, 2)

    def test_optional_when_disabled(self):
        with patch.object(sys, "argv", ["app", "--assets-conf", "dummy.yaml"]):
            config = ApplicationConfig()
            assert config.historical_data_dir_path is None
