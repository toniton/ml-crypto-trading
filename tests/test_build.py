import unittest
from unittest.mock import MagicMock, patch

from main import main


class TestBuildAndStartup(unittest.TestCase):

    def test_imports(self):
        # pylint: disable=import-outside-toplevel, unused-import
        try:
            import main
            import server.web_server
            import src.application
        except ImportError as e:
            self.fail(f"Failed to import modules: {e}")

    @patch('main.AssetsConfig')
    @patch('main.ApplicationConfig')
    @patch('main.threading.Thread')
    @patch('main.Application')
    @patch('main.EnvironmentConfig')
    def test_main_startup(
            self, mock_environment_cls, mock_application_cls,
            mock_thread, mock_app_config_cls, mock_assets_config_cls
    ):
        # Mock configs
        mock_env_config_instance = MagicMock()
        mock_environment_cls.return_value = mock_env_config_instance

        mock_app_config_instance = MagicMock()
        mock_app_config_cls.return_value = mock_app_config_instance

        mock_assets_config_instance = MagicMock()
        mock_assets_config_cls.return_value = mock_assets_config_instance

        # Run main
        main()

        # Check Application instantiated with configs
        mock_application_cls.assert_called_once()
        call_args = mock_application_cls.call_args
        self.assertEqual(call_args.kwargs['environment_config'], mock_env_config_instance)
        self.assertEqual(call_args.kwargs['application_config'], mock_app_config_instance)
        self.assertEqual(call_args.kwargs['assets_config'], mock_assets_config_instance)

        # Check Thread started
        self.assertEqual(mock_thread.call_count, 1)
        mock_thread_instance = mock_thread.return_value
        mock_thread_instance.start.assert_called_once()
