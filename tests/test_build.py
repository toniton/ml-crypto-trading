import unittest
from queue import Queue
from unittest.mock import MagicMock, patch

from app_server import AppServer
from main import main
from server.web_server import WebServer


class TestBuildAndStartup(unittest.TestCase):

    def test_imports(self):
        # pylint: disable=import-outside-toplevel, unused-import
        try:
            import main
            import app_server
            import server.web_server
            import src.application
        except ImportError as e:
            self.fail(f"Failed to import modules: {e}")

    def test_component_initialization(self):
        q = Queue()
        try:
            app = AppServer(q)
            self.assertIsInstance(app, AppServer)
        except Exception as e:
            self.fail(f"Failed to initialize AppServer: {e}")

        try:
            web = WebServer(q)
            self.assertIsInstance(web, WebServer)
        except Exception as e:
            self.fail(f"Failed to initialize WebServer: {e}")

    @patch('main.webbrowser.open')
    @patch('main.threading.Thread')
    @patch('main.WebServer')
    @patch('main.AppServer')
    def test_main_startup(self, mock_app_server_cls, mock_web_server_cls, mock_thread, mock_browser_open):
        mock_web_instance = MagicMock()
        mock_web_server_cls.return_value = mock_web_instance

        mock_app_instance = MagicMock()
        mock_app_server_cls.return_value = mock_app_instance

        main()

        mock_web_server_cls.assert_called_once()
        mock_app_server_cls.assert_called_once()

        self.assertEqual(mock_thread.call_count, 2)

        calls = mock_thread.call_args_list
        targets = [call_args.kwargs.get('target') for call_args in calls]

        self.assertIn(mock_web_instance.run, targets)
        self.assertIn(mock_app_instance.startup, targets)

        mock_thread_instance = mock_thread.return_value
        self.assertEqual(mock_thread_instance.start.call_count, 2)

        mock_browser_open.assert_called_once_with('http://localhost:5555')
