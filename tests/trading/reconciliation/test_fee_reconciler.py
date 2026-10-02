import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.fees import Fees
from api.interfaces.timeframe import Timeframe
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.reconciliation.models.discrepancy import (
    DiscrepancySeverity,
    DiscrepancyType,
)
from src.trading.reconciliation.reconcilers.fee_reconciler import FeeReconciler


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


class TestFeeReconciler(unittest.TestCase):
    def setUp(self):
        self.mock_fees_manager = MagicMock()
        self.reconciler = FeeReconciler(fees_manager=self.mock_fees_manager)
        self.test_asset = create_test_asset()

    def test_reconcile_valid_fees_no_discrepancy(self):
        self.mock_fees_manager.get_instrument_fees.return_value = Fees(
            maker_fee_pct=Decimal("0.001"),
            taker_fee_pct=Decimal("0.002"),
        )
        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])
        self.assertEqual(len(discrepancies), 0)

    def test_reconcile_invalid_negative_fee_discrepancy(self):
        self.mock_fees_manager.get_instrument_fees.return_value = Fees(
            maker_fee_pct=Decimal("-0.005"),
            taker_fee_pct=Decimal("0.002"),
        )
        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])
        self.assertEqual(len(discrepancies), 1)
        self.assertEqual(discrepancies[0].discrepancy_type, DiscrepancyType.FEE_MISMATCH)
        self.assertEqual(discrepancies[0].severity, DiscrepancySeverity.WARNING)
