import unittest
from unittest.mock import MagicMock, patch

from main import main


class TestBuildAndStartup(unittest.TestCase):

    def test_imports(self):
        # pylint: disable=import-outside-toplevel, unused-import
        try:
            import main
            import src.application
        except ImportError as e:
            self.fail(f"Failed to import modules: {e}")

    @patch('main.AssetsConfig')
    @patch('main.ApplicationConfig')
    @patch('main.Application')
    @patch('main.EnvironmentConfig')
    def test_main_startup(
            self, mock_environment_cls, mock_application_cls,
            mock_app_config_cls, mock_assets_config_cls
    ):
        # Mock configs
        mock_env_config_instance = MagicMock()
        mock_environment_cls.return_value = mock_env_config_instance

        mock_app_config_instance = MagicMock()
        mock_app_config_cls.return_value = mock_app_config_instance
        # Ensure backtest_mode is False so we enter the Application path
        mock_app_config_instance.backtest_mode = False

        mock_assets_config_instance = MagicMock()
        mock_assets_config_cls.return_value = mock_assets_config_instance

        # Mock loop condition to exit immediately
        mock_application_instance = mock_application_cls.return_value
        # make is_running.is_set return False so the while loop terminates
        mock_application_instance.is_running.is_set.return_value = False

        # Run main
        main()

        # Check Application instantiated with configs
        mock_application_cls.assert_called_once()
        call_args = mock_application_cls.call_args
        self.assertEqual(call_args.kwargs['environment_config'], mock_env_config_instance)
        self.assertEqual(call_args.kwargs['application_config'], mock_app_config_instance)
        self.assertEqual(call_args.kwargs['assets_config'], mock_assets_config_instance)

        # Check startup called
        mock_application_instance.startup.assert_called_once()
