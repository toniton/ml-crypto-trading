import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from api.interfaces.trading_context import TradingContext
from src.core.severity import Severity
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.reconciliation.models.discrepancy import (
    DiscrepancyType,
)
from src.trading.reconciliation.reconcilers.position_reconciler import (
    PositionReconciler,
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


class TestPositionReconciler(unittest.TestCase):
    def setUp(self):
        self.mock_session_manager = MagicMock()
        self.mock_account_manager = MagicMock()
        self.reconciler = PositionReconciler(
            session_manager=self.mock_session_manager,
            account_manager=self.mock_account_manager,
            critical_threshold=Decimal("0.001"),
            dust_threshold=Decimal("0.00000001"),
        )
        self.test_asset = create_test_asset()

    def test_reconcile_position_mismatch_critical(self):
        trading_ctx = TradingContext(
            ticker_symbol="BTC_USD",
            exchange="CRYPTO_DOT_COM",
            starting_balance=Decimal("1000"),
            position_qty=Decimal("1.5"),
        )
        self.mock_session_manager.get_trading_context.return_value = trading_ctx
        self.mock_account_manager.get_base_balance.return_value = AccountBalance(
            "BTC", Decimal("0.5")
        )

        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])

        self.assertEqual(len(discrepancies), 1)
        disc = discrepancies[0]
        self.assertEqual(disc.discrepancy_type, DiscrepancyType.POSITION_MISMATCH)
        self.assertEqual(disc.severity, Severity.CRITICAL)
        self.assertEqual(disc.difference, Decimal("-1.0"))
        # Verify authoritative sync
        self.assertEqual(trading_ctx.position_qty, Decimal("0.5"))

    def test_reconcile_position_matching(self):
        trading_ctx = TradingContext(
            ticker_symbol="BTC_USD",
            exchange="CRYPTO_DOT_COM",
            starting_balance=Decimal("1000"),
            position_qty=Decimal("1.0"),
        )
        self.mock_session_manager.get_trading_context.return_value = trading_ctx
        self.mock_account_manager.get_base_balance.return_value = AccountBalance(
            "BTC", Decimal("1.0")
        )

        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])

        self.assertEqual(len(discrepancies), 0)

    def test_reconcile_position_dust_below_min_quantity_is_warning_not_critical(self):
        # min_quantity of test_asset is 0.01
        trading_ctx = TradingContext(
            ticker_symbol="BTC_USD",
            exchange="CRYPTO_DOT_COM",
            starting_balance=Decimal("1000"),
            position_qty=Decimal("1.000"),
        )
        self.mock_session_manager.get_trading_context.return_value = trading_ctx
        # Exchange has 1.005 (difference 0.005, which is > 0.001 critical_threshold but < 0.01 min_quantity)
        self.mock_account_manager.get_base_balance.return_value = AccountBalance(
            "BTC", Decimal("1.005")
        )

        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])

        self.assertEqual(len(discrepancies), 1)
        disc = discrepancies[0]
        self.assertEqual(disc.severity, Severity.WARNING)
        self.assertEqual(disc.action_taken, "LOCAL_STATE_SYNCED")
        self.assertEqual(trading_ctx.position_qty, Decimal("1.005"))
