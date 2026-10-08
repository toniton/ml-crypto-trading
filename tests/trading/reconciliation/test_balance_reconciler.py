import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from src.core.severity import Severity
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.reconciliation.models.discrepancy import (
    DiscrepancyType,
)
from src.trading.reconciliation.reconcilers.balance_reconciler import (
    BalanceReconciler,
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


class TestBalanceReconciler(unittest.TestCase):
    def setUp(self):
        self.mock_account_manager = MagicMock()
        self.mock_rest_manager = MagicMock()
        self.mock_session_manager = MagicMock()
        self.reconciler = BalanceReconciler(
            account_manager=self.mock_account_manager,
            rest_manager=self.mock_rest_manager,
            session_manager=self.mock_session_manager,
            critical_threshold=Decimal("1.00"),
            warning_threshold=Decimal("0.0001"),
        )
        self.test_asset = create_test_asset()

    def test_reconcile_critical_balance_mismatch(self):
        self.mock_account_manager.balances = {
            "CRYPTO_DOT_COM": {
                "USD": AccountBalance("USD", Decimal("7610.00")),
            }
        }
        self.mock_rest_manager.get_account_balance.return_value = [
            AccountBalance("USD", Decimal("23.14")),
        ]

        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])

        self.assertEqual(len(discrepancies), 1)
        disc = discrepancies[0]
        self.assertEqual(disc.discrepancy_type, DiscrepancyType.BALANCE_MISMATCH)
        self.assertEqual(disc.severity, Severity.CRITICAL)
        self.assertEqual(disc.exchange, "CRYPTO_DOT_COM")
        self.assertEqual(disc.asset_or_currency, "USD")
        self.assertEqual(disc.difference, Decimal("-7586.86"))
        self.assertEqual(disc.action_taken, "TRADING_PAUSED_AND_LOCAL_SYNCED")

        self.mock_account_manager._cache_balances.assert_called_once()
        self.mock_session_manager.update_available_balance.assert_called_with(
            self.test_asset.key, Decimal("23.14")
        )

    def test_reconcile_warning_balance_mismatch(self):
        self.mock_account_manager.balances = {
            "CRYPTO_DOT_COM": {
                "USD": AccountBalance("USD", Decimal("100.00")),
            }
        }
        self.mock_rest_manager.get_account_balance.return_value = [
            AccountBalance("USD", Decimal("99.50")),
        ]

        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])

        self.assertEqual(len(discrepancies), 1)
        disc = discrepancies[0]
        self.assertEqual(disc.severity, Severity.WARNING)
        self.assertEqual(disc.difference, Decimal("-0.50"))
        self.assertEqual(disc.action_taken, "LOCAL_STATE_SYNCED")

    def test_reconcile_no_discrepancy_when_matching(self):
        self.mock_account_manager.balances = {
            "CRYPTO_DOT_COM": {
                "USD": AccountBalance("USD", Decimal("100.00")),
            }
        }
        self.mock_rest_manager.get_account_balance.return_value = [
            AccountBalance("USD", Decimal("100.00")),
        ]

        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])

        self.assertEqual(len(discrepancies), 0)

    def test_reconcile_ignores_unmanaged_currencies(self):
        self.mock_account_manager.balances = {
            "CRYPTO_DOT_COM": {
                "USD": AccountBalance("USD", Decimal("100.00")),
            }
        }
        # Exchange returns unmanaged CRO and DOGE balances
        self.mock_rest_manager.get_account_balance.return_value = [
            AccountBalance("USD", Decimal("100.00")),
            AccountBalance("CRO", Decimal("500.00")),
            AccountBalance("DOGE", Decimal("1000.00")),
        ]

        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])

        # No discrepancy should be generated for unmanaged CRO/DOGE
        self.assertEqual(len(discrepancies), 0)

    def test_reconcile_ignores_uninitialized_local_currencies(self):
        self.mock_account_manager.balances = {
            "CRYPTO_DOT_COM": {}
        }
        self.mock_rest_manager.get_account_balance.return_value = [
            AccountBalance("USD", Decimal("100.00")),
        ]

        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])

        # When local balance is not yet initialized, it is discovered/synced without critical discrepancy
        self.assertEqual(len(discrepancies), 0)
