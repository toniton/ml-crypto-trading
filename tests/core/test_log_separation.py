import unittest
import logging
import os
import uuid
import shutil
from unittest.mock import MagicMock

from src.core.logging.manager import LoggingManager
from src.core.logging.factory import LoggingFactory


class TestLogSeparation(unittest.TestCase):
    def setUp(self):
        LoggingManager.reset()
        mock_config = MagicMock()
        self.test_log_dir = os.path.join(os.getcwd(), f'test_logs_{uuid.uuid4().hex}')
        mock_config.log_dir = self.test_log_dir
        mock_config.log_level = 'INFO'
        manager = LoggingManager.get_instance(mock_config)
        # pylint: disable=protected-access
        self.app_log = manager.get_log_file_path('application')
        self.trading_log = manager.get_log_file_path('trading')
        self.audit_log = manager.get_log_file_path('audit')

        for log_file in [self.app_log, self.trading_log, self.audit_log]:
            if os.path.exists(log_file):
                os.remove(log_file)

        manager.setup_logging()

    def tearDown(self):
        if os.path.exists(self.test_log_dir):
            shutil.rmtree(self.test_log_dir)
        logging.shutdown()

    def test_application_logs_go_to_application_log(self):
        app_logger = LoggingFactory.get_application_logger('TestApp')
        app_logger.info('Test application message')

        for handler in app_logger.parent.handlers:
            handler.flush()

        self.assertTrue(os.path.exists(self.app_log))
        with open(self.app_log, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn('Test application message', content)
            self.assertIn('application', content)
            self.assertIn('TestApp', content)

    def test_trading_logs_go_to_trading_log(self):
        trading_logger = LoggingFactory.get_trading_logger('TestTrading')
        trading_logger.info('Test trading message')

        for handler in trading_logger.parent.handlers:
            handler.flush()

        self.assertTrue(os.path.exists(self.trading_log))
        with open(self.trading_log, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn('Test trading message', content)
            self.assertIn('trading', content)
            self.assertIn('TestTrading', content)

    def test_logs_are_separated(self):
        app_logger = LoggingFactory.get_application_logger('AppTest')
        trading_logger = LoggingFactory.get_trading_logger('TradingTest')

        app_logger.info('Application specific log')
        trading_logger.info('Trading specific log')

        for logger in [app_logger.parent, trading_logger.parent]:
            for handler in logger.handlers:
                handler.flush()

        with open(self.app_log, 'r', encoding='utf-8') as f:
            app_content = f.read()
            self.assertIn('Application specific log', app_content)
            self.assertNotIn('Trading specific log', app_content)

        with open(self.trading_log, 'r', encoding='utf-8') as f:
            trading_content = f.read()
            self.assertIn('Trading specific log', trading_content)
            self.assertNotIn('Application specific log', trading_content)

    def test_log_format_is_consistent(self):
        app_logger = LoggingFactory.get_application_logger('FormatTest')
        app_logger.info('Format test message')

        for handler in app_logger.parent.handlers:
            handler.flush()

        with open(self.app_log, 'r', encoding='utf-8') as f:
            log_line = f.readline().strip()
            parts = log_line.split(' - ')

            self.assertEqual(len(parts), 4)
            self.assertIn('application', parts[1])
            self.assertIn('FormatTest', parts[1])
            self.assertEqual(parts[2], 'INFO')
            self.assertEqual(parts[3], 'Format test message')
