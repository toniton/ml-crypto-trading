import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from src.clients.ccxt.ccxt_rest_builder import CCXTExchangeRestBuilder
from src.clients.ccxt.ccxt_rest_service import CCXTExchangeRestService


class TestCCXTRestExecution(unittest.TestCase):
    @patch('src.clients.ccxt_rest_service.EnvironmentConfig')
    @patch('ccxt.binance')
    def setUp(self, mock_binance, mock_env_config):
        self.mock_exchange = MagicMock()
        mock_binance.return_value = self.mock_exchange
        self.service = CCXTExchangeRestService('binance')
        self.builder = CCXTExchangeRestBuilder('binance')

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
        from api.interfaces.order import TradeAction
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


if __name__ == '__main__':
    unittest.main()
