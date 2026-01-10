import unittest
import os
import csv
import uuid
import shutil
import logging
from unittest.mock import MagicMock

from src.core.logging.audit_logging_mixin import AuditLoggingMixin
from src.core.logging.manager import LoggingManager
from api.interfaces.market_data import MarketData


class TestAuditClass(AuditLoggingMixin):
    pass


class TestAuditLogging(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.NOTSET)
        LoggingManager.reset()
        mock_config = MagicMock()
        self.test_log_dir = os.path.join(os.getcwd(), f'test_logs_{uuid.uuid4().hex}')
        mock_config.log_dir = self.test_log_dir
        mock_config.log_level = 'INFO'

        manager = LoggingManager.get_instance(mock_config)
        # pylint: disable=protected-access
        self.audit_log = manager.get_log_file_path('audit')
        if os.path.exists(self.audit_log):
            os.remove(self.audit_log)
        manager.setup_logging()

    def tearDown(self):
        LoggingManager.reset()
        if os.path.exists(self.test_log_dir):
            shutil.rmtree(self.test_log_dir)

    def test_audit_log_has_correct_csv_header(self):
        obj = TestAuditClass()
        _ = obj.audit_logger
        for handler in obj.audit_logger.handlers:
            handler.flush()

        with open(self.audit_log, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            header = next(reader)

            expected_header = [
                'timestamp', 'asset', 'event_type', 'action',
                'close_price', 'high_price', 'low_price', 'volume', 'context'
            ]
            self.assertEqual(header, expected_header)

    def test_asset_specific_audit_logs(self):
        obj = TestAuditClass()

        market_data1 = MarketData(
            close_price='42500.50',
            high_price='42600.00',
            low_price='42400.00',
            volume='1250000',
            timestamp=1735862595789
        )

        market_data2 = MarketData(
            close_price='42600.00',
            high_price='42700.00',
            low_price='42500.00',
            volume='1300000',
            timestamp=1735862655789
        )

        # Log for BTC/USD
        obj.log_audit_event(
            event_type='trade_executed',
            asset='BTC/USD',
            action='BUY',
            market_data=market_data1
        )

        # Log for ETH/USD
        obj.log_audit_event(
            event_type='trade_executed',
            asset='ETH/USD',
            action='SELL',
            market_data=market_data2
        )

        manager = LoggingManager.get_instance()
        btc_log = manager.get_log_file_path('audit', 'BTC/USD')
        eth_log = manager.get_log_file_path('audit', 'ETH/USD')

        self.assertTrue(os.path.exists(btc_log))
        self.assertTrue(os.path.exists(eth_log))

        with open(btc_log, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['asset'], 'BTC/USD')

        with open(eth_log, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['asset'], 'ETH/USD')

    def test_audit_event_creates_valid_csv_row(self):
        obj = TestAuditClass()

        market_data = MarketData(
            close_price='42500.50',
            high_price='42600.00',
            low_price='42400.00',
            volume='1250000',
            timestamp=1735862595789
        )

        asset = 'BTC/USD'
        obj.log_audit_event(
            event_type='trade_decision',
            asset=asset,
            action='BUY',
            market_data=market_data,
            context='consensus_reached'
        )

        manager = LoggingManager.get_instance()
        asset_log = manager.get_log_file_path('audit', asset)

        with open(asset_log, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            row = next(reader)

            self.assertEqual(row['asset'], 'BTC/USD')
            self.assertEqual(row['event_type'], 'trade_decision')
            self.assertEqual(row['action'], 'BUY')
            self.assertEqual(row['close_price'], '42500.50')
            self.assertEqual(row['high_price'], '42600.00')
            self.assertEqual(row['low_price'], '42400.00')
            self.assertEqual(row['volume'], '1250000')
            self.assertEqual(row['context'], 'consensus_reached')

    def test_audit_event_without_market_data(self):
        obj = TestAuditClass()

        asset = 'SYSTEM'
        obj.log_audit_event(
            event_type='system_event',
            asset=asset,
            action='INIT',
            market_data=None,
            context='application_startup'
        )

        manager = LoggingManager.get_instance()
        asset_log = manager.get_log_file_path('audit', asset)

        with open(asset_log, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            row = next(reader)

            self.assertEqual(row['asset'], 'SYSTEM')
            self.assertEqual(row['event_type'], 'system_event')
            self.assertEqual(row['action'], 'INIT')
            self.assertEqual(row['close_price'], '')
            self.assertEqual(row['high_price'], '')
            self.assertEqual(row['low_price'], '')
            self.assertEqual(row['volume'], '')
            self.assertEqual(row['context'], 'application_startup')
