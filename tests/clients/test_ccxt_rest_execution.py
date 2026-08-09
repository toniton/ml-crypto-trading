import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from api.interfaces.order import TradeAction
from src.clients.ccxt.ccxt_rest_builder import CCXTExchangeRestBuilder
from src.clients.ccxt.ccxt_rest_service import CCXTExchangeRestService
from src.core.managers.exchange_rest_manager import ExchangeProvidersEnum


class TestCCXTRestExecution(unittest.TestCase):
    @patch('src.clients.ccxt.ccxt_rest_service.EnvironmentConfig')
    @patch('ccxt.binance')
    def setUp(self, mock_binance, _mock_env_config):
        self.mock_exchange = MagicMock()
        mock_binance.return_value = self.mock_exchange
        self.service = CCXTExchangeRestService(ExchangeProvidersEnum.CCXT_BINANCE)
        self.builder = CCXTExchangeRestBuilder(ExchangeProvidersEnum.CCXT_BINANCE.value)

    def test_execute_market_data(self):
        self.mock_exchange.fetch_ticker.return_value = {
            'baseVolume': 100,
            'high': 51000,
            'low': 49000,
            'close': 50000,
            'timestamp': 1600000000000
        }
        self.builder.market_data('BTC/USDT')
        self.service.execute(self.builder)
        self.mock_exchange.fetch_ticker.assert_called_once_with(symbol='BTC/USDT')

    def test_execute_create_order(self):
        self.mock_exchange.create_order.return_value = {
            'id': '123',
            'clientOrderId': 'test-uuid',
            'symbol': 'BTC/USDT',
            'price': 50000,
            'amount': 1.5,
            'side': 'buy',
            'timestamp': 1600000000000,
            'status': 'open'
        }
        self.builder.create_order(
            uuid='test-uuid',
            ticker_symbol='BTC/USDT',
            quantity='1.5',
            price=Decimal('50000'),
            trade_action=TradeAction.BUY
        )
        self.service.execute(self.builder)
        self.mock_exchange.create_order.assert_called_once_with(
            symbol='BTC/USDT',
            type='limit',
            side='buy',
            amount=1.5,
            price=50000.0,
            params={'clientOrderId': 'test-uuid'}
        )

    def test_execute_get_open_orders(self):
        self.mock_exchange.fetch_open_orders.return_value = [
            {
                'id': '123',
                'clientOrderId': 'test-uuid',
                'symbol': 'BTC/USDT',
                'price': 50000,
                'amount': 1.5,
                'side': 'buy',
                'timestamp': 1600000000000,
                'status': 'open'
            },
            {
                'id': '124',
                'clientOrderId': 'test-uuid-2',
                'symbol': 'BTC/USDT',
                'price': 49000,
                'amount': 0.5,
                'side': 'sell',
                'timestamp': 1600000000000,
                'status': 'open'
            }
        ]
        self.builder.get_open_orders()
        result = self.service.execute(self.builder)
        self.mock_exchange.fetch_open_orders.assert_called_once_with()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].uuid, 'test-uuid')
        self.assertEqual(result[0].status.value, 'PENDING')
        self.assertEqual(result[1].trade_action.value, 'SELL')

    def test_execute_get_open_orders_with_symbol(self):
        self.mock_exchange.fetch_open_orders.return_value = []
        self.builder.get_open_orders('BTC/USDT')
        self.service.execute(self.builder)
        self.mock_exchange.fetch_open_orders.assert_called_once_with(symbol='BTC/USDT')
