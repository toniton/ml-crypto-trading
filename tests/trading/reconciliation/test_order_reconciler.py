import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.order import Order
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.reconciliation.models.discrepancy import (
    DiscrepancySeverity,
    DiscrepancyType,
)
from src.trading.reconciliation.reconcilers.order_reconciler import (
    OrderReconciler,
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


class TestOrderReconciler(unittest.TestCase):
    def setUp(self):
        self.mock_order_manager = MagicMock()
        self.mock_rest_manager = MagicMock()
        self.mock_rest_manager.get_registered_services.return_value = ["CRYPTO_DOT_COM"]
        self.reconciler = OrderReconciler(
            order_manager=self.mock_order_manager,
            rest_manager=self.mock_rest_manager,
        )
        self.test_asset = create_test_asset()

    def test_reconcile_status_mismatch(self):
        local_order = Order(
            uuid="ord-123",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("50000"),
            quantity="0.1",
            trade_action=TradeAction.BUY,
            created_time=100.0,
            status=OrderStatus.PENDING,
        )
        exchange_order = Order(
            uuid="ord-123",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("50000"),
            quantity="0.1",
            trade_action=TradeAction.BUY,
            created_time=100.0,
            status=OrderStatus.COMPLETED,
            fill_price=Decimal("50000"),
            fees=Decimal("1.5"),
            executed_time=105.0,
        )

        self.mock_order_manager._get_non_terminal_orders.return_value = [local_order]
        self.mock_order_manager.get_order.return_value = exchange_order
        self.mock_order_manager.get_open_orders.return_value = []

        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])

        self.assertEqual(len(discrepancies), 1)
        disc = discrepancies[0]
        self.assertEqual(disc.discrepancy_type, DiscrepancyType.ORDER_STATUS_MISMATCH)
        self.assertEqual(disc.severity, DiscrepancySeverity.WARNING)
        self.assertEqual(local_order.status, OrderStatus.COMPLETED)
        self.assertEqual(local_order.fill_price, Decimal("50000"))
        self.mock_order_manager._save_orders_to_database.assert_called_with([local_order])

    def test_reconcile_orphan_order_detected(self):
        self.mock_order_manager._get_non_terminal_orders.return_value = []
        orphan_order = Order(
            uuid="orphan-999",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("49000"),
            quantity="0.2",
            trade_action=TradeAction.BUY,
            created_time=100.0,
            status=OrderStatus.PENDING,
        )
        self.mock_order_manager.get_open_orders.return_value = [orphan_order]

        discrepancies = self.reconciler.reconcile("CRYPTO_DOT_COM", [self.test_asset])

        self.assertEqual(len(discrepancies), 1)
        disc = discrepancies[0]
        self.assertEqual(disc.discrepancy_type, DiscrepancyType.ORPHAN_ORDER_DETECTED)
        self.assertEqual(disc.severity, DiscrepancySeverity.CRITICAL)
        self.assertEqual(disc.action_taken, "MANUAL_REVIEW_REQUIRED")
