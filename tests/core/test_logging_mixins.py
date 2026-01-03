import csv
import unittest
import logging
import os
import uuid
import shutil
from unittest.mock import MagicMock

from api.interfaces.market_data import MarketData
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.core.logging.trading_logging_mixin import TradingLoggingMixin
from src.core.logging.audit_logging_mixin import AuditLoggingMixin
from src.core.logging.manager import LoggingManager


class TestClass(ApplicationLoggingMixin):
    pass


class TradingTestClass(TradingLoggingMixin):
    pass


class AuditTestClass(AuditLoggingMixin):
    pass


class TestLoggingMixins(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.NOTSET)
        LoggingManager.reset()
        mock_config = MagicMock()
        self.test_log_dir = os.path.join(os.getcwd(), f'test_logs_{uuid.uuid4().hex}')
        mock_config.log_dir = self.test_log_dir
        mock_config.log_level = 'INFO'

        # pylint: disable=protected-access
        self.audit_log = LoggingManager.get_instance(mock_config).get_log_file_path('audit')
        if os.path.exists(self.audit_log):
            os.remove(self.audit_log)
        LoggingManager.get_instance().setup_logging()

    def tearDown(self):
        if os.path.exists(self.test_log_dir):
            shutil.rmtree(self.test_log_dir)
        logging.shutdown()

    def test_application_logging_mixin_provides_logger(self):
        obj = TestClass()
        self.assertIsNotNone(obj.app_logger)
        self.assertIsInstance(obj.app_logger, logging.Logger)
        self.assertTrue(obj.app_logger.name.startswith('application.'))
        self.assertTrue(obj.app_logger.name.endswith('.TestClass'))

    def test_trading_logging_mixin_provides_logger(self):
        obj = TradingTestClass()
        self.assertIsNotNone(obj.trading_logger)
        self.assertIsInstance(obj.trading_logger, logging.Logger)
        self.assertTrue(obj.trading_logger.name.startswith('trading.'))
        self.assertTrue(obj.trading_logger.name.endswith('.TradingTestClass'))

    def test_audit_logging_mixin_provides_logger(self):
        obj = AuditTestClass()
        self.assertIsNotNone(obj.audit_logger)
        self.assertIsInstance(obj.audit_logger, logging.Logger)
        self.assertTrue(obj.audit_logger.name.startswith('audit.'))

    def test_multiple_mixins_on_same_class(self):
        class Combined(ApplicationLoggingMixin, TradingLoggingMixin, AuditLoggingMixin):
            pass

        obj = Combined()
        self.assertIsNotNone(obj.app_logger)
        self.assertIsNotNone(obj.trading_logger)
        self.assertIsNotNone(obj.audit_logger)

        self.assertTrue(obj.app_logger.name.startswith('application.'))
        self.assertTrue(obj.app_logger.name.endswith('.Combined'))
        self.assertTrue(obj.trading_logger.name.startswith('trading.'))
        self.assertTrue(obj.trading_logger.name.endswith('.Combined'))
        self.assertTrue(obj.audit_logger.name.startswith('audit.'))

    def test_audit_mixin_creates_csv_header(self):
        obj = AuditTestClass()
        _ = obj.audit_logger
        for handler in obj.audit_logger.handlers:
            handler.flush()

        self.assertTrue(os.path.exists(self.audit_log))

        with open(self.audit_log, 'r', encoding='utf-8') as f:
            header = f.readline().strip()
            self.assertEqual(
                header,
                'timestamp,asset,event_type,action,close_price,high_price,low_price,volume,context'
            )

    def test_log_audit_event_writes_csv_row(self):
        obj = AuditTestClass()

        market_data = MarketData(
            close_price='42500.50',
            high_price='42600.00',
            low_price='42400.00',
            volume='1250000',
            timestamp=1735862595789
        )

        asset = 'BTC/USD'
        obj.log_audit_event(
            event_type='trade_executed',
            asset=asset,
            action='BUY',
            market_data=market_data,
            context='price=42500.50,quantity=0.00001'
        )

        manager = LoggingManager.get_instance()
        asset_log = manager.get_log_file_path('audit', asset)

        with open(asset_log, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            lines = [l for l in list(reader) if l]  # Ignore empty lines
            self.assertEqual(len(lines), 2)
            fields = lines[1]

            self.assertEqual(fields[1], 'BTC/USD')
            self.assertEqual(fields[2], 'trade_executed')
            self.assertEqual(fields[3], 'BUY')
            self.assertEqual(fields[4], '42500.50')
            self.assertEqual(fields[5], '42600.00')
            self.assertEqual(fields[6], '42400.00')
            self.assertEqual(fields[7], '1250000')
            self.assertEqual(fields[8], 'price=42500.50,quantity=0.00001')
