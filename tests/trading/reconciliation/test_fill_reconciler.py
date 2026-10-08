import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.order import Order
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.core.severity import Severity
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.reconciliation.models.discrepancy import (
    DiscrepancyType,
)
from src.trading.reconciliation.reconcilers.fill_reconciler import FillReconciler


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


class TestFillReconciler(unittest.TestCase):
    def setUp(self):
        self.mock_order_manager = MagicMock()
        self.mock_session_manager = MagicMock()
        self.reconciler = FillReconciler(
            order_manager=self.mock_order_manager,
            session_manager=self.mock_session_manager,
        )
        self.test_asset = create_test_asset()

    def test_reconcile_missing_fill_price_on_completed_order(self):
        completed_order_without_fill = Order(
            uuid="ord-completed-1",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("50000"),
            quantity="0.1",
            trade_action=TradeAction.BUY,
            created_time=100.0,
            status=OrderStatus.COMPLETED,
            fill_price=None,
        )
        self.mock_order_manager._database_manager = MagicMock()
        self.mock_order_manager._get_non_terminal_orders.return_value = [completed_order_without_fill]

        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])
        self.assertEqual(len(discrepancies), 1)
        self.assertEqual(discrepancies[0].discrepancy_type, DiscrepancyType.MISSING_FILL)
        self.assertEqual(discrepancies[0].severity, Severity.WARNING)

    def test_reconcile_completed_order_with_valid_fill_price(self):
        completed_order_with_fill = Order(
            uuid="ord-completed-2",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("50000"),
            quantity="0.1",
            trade_action=TradeAction.BUY,
            created_time=100.0,
            status=OrderStatus.COMPLETED,
            fill_price=Decimal("50000"),
        )
        self.mock_order_manager._database_manager = MagicMock()
        self.mock_order_manager._get_non_terminal_orders.return_value = [completed_order_with_fill]

        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])
        self.assertEqual(len(discrepancies), 0)
