from decimal import Decimal
import unittest
from unittest.mock import MagicMock, patch

from api.interfaces.trade_action import TradeAction
from src.configuration.exchanges_config import ExchangesConfig
from src.exchange.clients.cryptodotcom.cryptodotcom_rest_builder import CryptoDotComRestBuilder
from src.exchange.clients.cryptodotcom.cryptodotcom_rest_service import CryptoDotComRestService


class TestCryptoDotComRestService(unittest.TestCase):
    def setUp(self):
        self.config = MagicMock(spec=ExchangesConfig)
        self.config.crypto_dot_com = MagicMock()
        self.config.crypto_dot_com.rest_endpoint = "https://api.crypto.com"
        self.config.crypto_dot_com.api_key = "test_key"
        self.config.crypto_dot_com.secret_key = MagicMock()
        self.config.crypto_dot_com.secret_key.get_secret_value.return_value = "test_secret"

        # Patching ExchangesConfig class in the service module
        patcher = patch(
            'src.exchange.clients.cryptodotcom.cryptodotcom_rest_service.ExchangesConfig',
            return_value=self.config
        )
        self.mock_get_config = patcher.start()
        self.addCleanup(patcher.stop)

        self.service = CryptoDotComRestService()

    def test_get_provider_name(self):
        self.assertEqual(self.service.get_provider_name(), "CRYPTO_DOT_COM")

    def test_create_builder(self):
        builder = self.service.builder()
        self.assertIsInstance(builder, CryptoDotComRestBuilder)

    @patch('src.trading.helpers.request_helper.RequestHelper.execute_request')
    def test_execute_generic(self, mock_execute):
        mock_execute.return_value = {"result": "success"}
        builder = MagicMock(spec=CryptoDotComRestBuilder)

        # Mocking generic Mapper
        mock_mapper = MagicMock()
        mock_mapper.map.return_value = {"mapped": "result"}
        builder.mapper.return_value = mock_mapper

        builder.build_request.return_value = MagicMock()

        result = self.service.execute(builder)

        self.assertEqual(result, {"mapped": "result"})
        builder.build_request.assert_called_with("https://api.crypto.com")
        builder.sign.assert_called_with("test_key", "test_secret")
        mock_execute.assert_called_once()
        mock_mapper.map.assert_called_once()


class TestCryptoDotComRestBuilderOpenOrders(unittest.TestCase):
    def test_get_open_orders_endpoint(self):
        builder = CryptoDotComRestBuilder()
        builder.get_open_orders()
        endpoint = builder.get_endpoint()
        self.assertEqual(endpoint.path, "private/get-open-orders")
        self.assertTrue(endpoint.private)
        self.assertEqual(builder.get_params(), {})

    def test_get_open_orders_with_ticker(self):
        builder = CryptoDotComRestBuilder()
        builder.get_open_orders("BTC_USD")
        self.assertEqual(builder.get_params(), {"instrument_name": "BTC_USD"})

    def test_get_open_orders_uses_orders_mapper(self):
        builder = CryptoDotComRestBuilder()
        builder.get_open_orders()
        self.assertIsNotNone(builder.mapper())


class TestCryptoDotComRestBuilderCreateOrder(unittest.TestCase):
    def test_create_order_sets_correct_endpoint(self):
        builder = CryptoDotComRestBuilder()
        builder.create_order(
            uuid="cb18b6d9-8fa6-46d2-b072-a781a574990e",
            ticker_symbol="CRO_USD",
            quantity="19",
            price=Decimal("0.058750"),
            trade_action=TradeAction.BUY,
        )
        self.assertEqual(builder.get_endpoint().path, "private/create-order")

    def test_create_order_sets_correct_params(self):
        builder = CryptoDotComRestBuilder()
        builder.create_order(
            uuid="cb18b6d9-8fa6-46d2-b072-a781a574990e",
            ticker_symbol="CRO_USD",
            quantity="19",
            price=Decimal("0.058750"),
            trade_action=TradeAction.BUY,
        )
        self.assertEqual(builder.get_params(), {
            "instrument_name": "CRO_USD",
            "side": "BUY",
            "type": "LIMIT",
            "price": "0.058750",
            "quantity": "19",
            "client_oid": "cb18b6d9-8fa6-46d2-b072-a781a574990e",
            "time_in_force": "GOOD_TILL_CANCEL",
        })

    def test_create_order_accepts_audit_metadata_kwargs_without_error(self):
        builder = CryptoDotComRestBuilder()
        builder.create_order(
            uuid="cb18b6d9-8fa6-46d2-b072-a781a574990e",
            ticker_symbol="CRO_USD",
            quantity="19",
            price=Decimal("0.058750"),
            trade_action=TradeAction.BUY,
            metadata={
                "commit_hash": "f065cc98755278e106e0f5ea5e0064a39df2c7706645e04c2eb85744e47bd18a",
                "winning_strategy": "BreakoutBuy",
                "strategy_votes": {"HammerAccumulationStrategy": "TRUE", "BreakoutBuy": "TRUE"},
                "strategy_attributions": {"HammerAccumulationStrategy": 0.5, "BreakoutBuy": 0.5},
            },
        )
        self.assertEqual(builder.get_params()["client_oid"], "cb18b6d9-8fa6-46d2-b072-a781a574990e")
