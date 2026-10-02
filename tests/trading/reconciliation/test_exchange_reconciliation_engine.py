import time
import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.events.domain_events import (
    ReconciliationCompletedEvent,
    ReconciliationDiscrepancyEvent,
)
from src.trading.protection.protection_manager import ProtectionManager
from src.trading.reconciliation.exchange_reconciliation_engine import (
    ExchangeReconciliationEngine,
)
from src.trading.reconciliation.models.discrepancy import (
    Discrepancy,
    DiscrepancySeverity,
    DiscrepancyType,
)


def create_test_asset(symbol="BTC_USD", exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM) -> Asset:
    return Asset(
        exchange=exchange,
        schedule=AssetSchedule.EVERY_MINUTE,
        quote_ticker_symbol="USD",
        base_ticker_symbol="BTC",
        quote_decimals=2,
        name=symbol,
        min_quantity=0.01,
        quantity_decimals=4,
        candles_timeframe=Timeframe.MIN1,
    )


class TestExchangeReconciliationEngine(unittest.TestCase):
    def setUp(self):
        self.mock_reconciler1 = MagicMock()
        self.mock_reconciler2 = MagicMock()
        self.mock_event_bus = MagicMock()
        self.protection_manager = ProtectionManager()
        self.mock_collector = MagicMock()
        self.test_asset = create_test_asset()

        self.engine = ExchangeReconciliationEngine(
            reconcilers=[self.mock_reconciler1, self.mock_reconciler2],
            assets=[self.test_asset],
            event_bus=self.mock_event_bus,
            protection_manager=self.protection_manager,
            order_lifecycle_collector=self.mock_collector,
            auto_pause_on_critical=True,
        )
        self.engine.RECONCILE_INTERVAL_SECONDS = 0.05

    def tearDown(self):
        self.engine.stop()

    def test_start_stop_lifecycle(self):
        self.engine.start()
        self.assertIsNotNone(self.engine._thread)
        self.assertTrue(self.engine._thread.is_alive())

        self.engine.stop()
        self.assertFalse(self.engine._thread.is_alive())

    def test_reconcile_all_emits_events_and_pauses_on_critical(self):
        critical_disc = Discrepancy(
            discrepancy_type=DiscrepancyType.BALANCE_MISMATCH,
            severity=DiscrepancySeverity.CRITICAL,
            exchange="CRYPTO_DOT_COM",
            asset_or_currency="USD",
            local_value="USD 7610.00",
            exchange_value="USD 23.14",
            difference=Decimal("-7586.86"),
            action_taken="TRADING_PAUSED_AND_LOCAL_SYNCED",
        )
        self.mock_reconciler1.reconcile.return_value = [critical_disc]
        self.mock_reconciler2.reconcile.return_value = []

        reports = self.engine.reconcile_all()

        self.assertEqual(len(reports), 1)
        self.assertTrue(reports[0].has_critical)
        self.assertTrue(self.protection_manager.is_paused)
        self.assertTrue(self.engine.has_critical_discrepancy("CRYPTO_DOT_COM", "USD"))

        # Verify event bus calls
        published_events = [call.args[0] for call in self.mock_event_bus.publish.call_args_list]
        discrepancy_events = [e for e in published_events if isinstance(e, ReconciliationDiscrepancyEvent)]
        completed_events = [e for e in published_events if isinstance(e, ReconciliationCompletedEvent)]

        self.assertEqual(len(discrepancy_events), 1)
        self.assertEqual(discrepancy_events[0].discrepancy_type, "BALANCE_MISMATCH")
        self.assertEqual(discrepancy_events[0].severity, "CRITICAL")
        self.assertEqual(len(completed_events), 1)
        self.assertEqual(completed_events[0].critical_count, 1)
        self.mock_collector.collect_and_record.assert_called_once()

    def test_trigger_starts_cycle(self):
        self.mock_reconciler1.reconcile.return_value = []
        self.mock_reconciler2.reconcile.return_value = []
        self.engine.start()
        self.engine.trigger()

        deadline = time.time() + 1
        while self.mock_reconciler1.reconcile.call_count == 0 and time.time() < deadline:
            time.sleep(0.01)

        self.assertGreaterEqual(self.mock_reconciler1.reconcile.call_count, 1)
