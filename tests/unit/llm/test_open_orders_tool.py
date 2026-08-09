import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.llm.tools.open_orders_tool import GetOpenOrdersTool
from src.trading.orders.order_manager import OrderManager


class TestGetOpenOrdersTool(unittest.TestCase):
    def _build_order(self, uuid="order-1", ticker_symbol="BTC_USD"):
        return Order(
            uuid=uuid,
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol=ticker_symbol,
            price=Decimal("51000.00"),
            quantity="0.1",
            trade_action=TradeAction.BUY,
            created_time=123456.78,
            status=OrderStatus.PENDING
        )

    def _build_asset(self, ticker_symbol="BTC_USD", exchange="CRYPTO_DOT_COM"):
        mock_asset = MagicMock()
        mock_asset.ticker_symbol = ticker_symbol
        mock_asset.exchange.value = exchange
        return mock_asset

    def test_tool_execution(self):
        mock_order_manager = MagicMock(spec=OrderManager)
        mock_order_manager.get_open_orders.return_value = [self._build_order()]

        tool = GetOpenOrdersTool(
            order_manager=mock_order_manager,
            assets=[self._build_asset()]
        )
        result = tool._run(exchange="CRYPTO_DOT_COM", ticker_symbol="BTC_USD")

        self.assertIn("Open Orders for BTC_USD on CRYPTO_DOT_COM (1)", result)
        self.assertIn("order-1", result)
        self.assertIn("qty=0.1", result)
        self.assertIn("price=51000", result)
        self.assertIn("status=PENDING", result)
        mock_order_manager.get_open_orders.assert_called_once_with("CRYPTO_DOT_COM", "BTC_USD")

    def test_tool_resolves_exchange_from_assets(self):
        mock_order_manager = MagicMock(spec=OrderManager)
        mock_order_manager.get_open_orders.return_value = [self._build_order()]

        tool = GetOpenOrdersTool(
            order_manager=mock_order_manager,
            assets=[self._build_asset()]
        )
        result = tool._run(ticker_symbol="BTC_USD")

        self.assertIn("Open Orders for BTC_USD (1)", result)
        mock_order_manager.get_open_orders.assert_called_once_with("CRYPTO_DOT_COM", "BTC_USD")

    def test_tool_all_open_orders_on_exchange(self):
        mock_order_manager = MagicMock(spec=OrderManager)
        mock_order_manager.get_open_orders.return_value = [self._build_order()]

        tool = GetOpenOrdersTool(
            order_manager=mock_order_manager,
            assets=[self._build_asset()]
        )
        result = tool._run(exchange="CRYPTO_DOT_COM")

        self.assertIn("Open Orders on CRYPTO_DOT_COM (1)", result)
        mock_order_manager.get_open_orders.assert_called_once_with("CRYPTO_DOT_COM", None)

    def test_tool_no_open_orders(self):
        mock_order_manager = MagicMock(spec=OrderManager)
        mock_order_manager.get_open_orders.return_value = []

        tool = GetOpenOrdersTool(
            order_manager=mock_order_manager,
            assets=[self._build_asset()]
        )
        result = tool._run(exchange="CRYPTO_DOT_COM", ticker_symbol="BTC_USD")

        self.assertIn("No open orders found for BTC_USD on CRYPTO_DOT_COM", result)

    def test_tool_no_configured_exchanges(self):
        mock_order_manager = MagicMock(spec=OrderManager)

        tool = GetOpenOrdersTool(
            order_manager=mock_order_manager,
            assets=[]
        )
        result = tool._run()

        self.assertIn("No configured exchanges", result)
        mock_order_manager.get_open_orders.assert_not_called()

    def test_tool_handles_exception(self):
        mock_order_manager = MagicMock(spec=OrderManager)
        mock_order_manager.get_open_orders.side_effect = RuntimeError("exchange down")

        tool = GetOpenOrdersTool(
            order_manager=mock_order_manager,
            assets=[self._build_asset()]
        )
        result = tool._run(exchange="CRYPTO_DOT_COM", ticker_symbol="BTC_USD")

        self.assertIn("Error fetching open orders from CRYPTO_DOT_COM: exchange down", result)


if __name__ == "__main__":
    unittest.main()
