import unittest
from decimal import Decimal

from src.trading.reconciliation.models.discrepancy import (
    Discrepancy,
    DiscrepancySeverity,
    DiscrepancyType,
)
from src.trading.reconciliation.models.reconciliation_report import (
    ReconciliationReport,
)


class TestReconciliationModels(unittest.TestCase):
    def test_discrepancy_creation_and_properties(self):
        disc = Discrepancy(
            discrepancy_type=DiscrepancyType.BALANCE_MISMATCH,
            severity=DiscrepancySeverity.CRITICAL,
            exchange="CRYPTO_DOT_COM",
            asset_or_currency="USD",
            local_value="USD 7610.00",
            exchange_value="USD 23.14",
            difference=Decimal("-7586.86"),
            action_taken="TRADING_PAUSED",
        )
        self.assertTrue(disc.is_critical)
        self.assertFalse(disc.is_warning)
        self.assertIn("BALANCE_MISMATCH", disc.format_alert())
        self.assertIn("CRYPTO_DOT_COM", disc.format_alert())
        self.assertIn("USD", disc.format_alert())
        self.assertIn("-7586.86", disc.format_alert())
        self.assertIn("TRADING_PAUSED", disc.format_alert())

    def test_reconciliation_report_aggregations(self):
        critical_disc = Discrepancy(
            discrepancy_type=DiscrepancyType.BALANCE_MISMATCH,
            severity=DiscrepancySeverity.CRITICAL,
            exchange="CRYPTO_DOT_COM",
            asset_or_currency="USD",
            local_value="USD 100",
            exchange_value="USD 50",
            difference=Decimal("-50"),
            action_taken="TRADING_PAUSED",
        )
        warning_disc = Discrepancy(
            discrepancy_type=DiscrepancyType.ORDER_STATUS_MISMATCH,
            severity=DiscrepancySeverity.WARNING,
            exchange="CRYPTO_DOT_COM",
            asset_or_currency="BTC",
            local_value="PENDING",
            exchange_value="FILLED",
            difference=None,
            action_taken="LOCAL_STATUS_UPDATED",
        )

        report = ReconciliationReport(
            cycle_id="test-cycle",
            exchange="CRYPTO_DOT_COM",
            started_at=100.0,
            finished_at=100.5,
            discrepancies=[critical_disc, warning_disc],
        )

        self.assertEqual(report.total_count, 2)
        self.assertTrue(report.has_critical)
        self.assertEqual(len(report.critical_discrepancies), 1)
        self.assertEqual(len(report.warning_discrepancies), 1)
        self.assertAlmostEqual(report.duration_ms, 500.0)
        self.assertIn("TRADING_PAUSED", report.actions_taken)
        self.assertIn("LOCAL_STATUS_UPDATED", report.actions_taken)
