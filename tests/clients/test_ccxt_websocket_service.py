import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.clients.ccxt.ccxt_websocket_service import CCXTExchangeWebSocketService
from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.subscription_data import SubscriptionVisibility
from src.core.managers.exchange_rest_manager import ExchangeProvidersEnum


class TestCCXTExchangeWebSocketService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = ExchangeProvidersEnum.CCXT_BINANCE
        self.service = CCXTExchangeWebSocketService(self.provider)

    def test_get_provider_name(self):
        self.assertEqual(self.service.get_provider_name(), "CCXT_BINANCE")

    @patch('threading.Thread')
    def test_connect(self, mock_thread):
        callback = MagicMock()
        self.service.connect(callback)

        self.assertTrue(self.service._is_running)
        self.assertEqual(self.service._callback, callback)
        mock_thread.assert_called_once()

    @patch('asyncio.run_coroutine_threadsafe')
    def test_subscribe(self, mock_run_coroutine):
        self.service._loop = MagicMock()
        self.service._loop.is_running.return_value = True

        mock_builder = MagicMock(spec=ExchangeWebSocketBuilder)
        mock_builder.get_subscription_data.return_value = MagicMock(
            payload={'type': 'ticker', 'symbol': 'BTC/USDT'},
            visibility=SubscriptionVisibility.PUBLIC
        )

        self.service.subscribe(mock_builder)

        self.assertIn('ticker_BTC/USDT', self.service._subscriptions)
        mock_run_coroutine.assert_called_once()
        # Silence RuntimeWarning: coroutine '...' was never awaited
        # Retrieve the coroutine passed to run_coroutine_threadsafe and close it
        coro = mock_run_coroutine.call_args[0][0]
        coro.close()

    @patch('asyncio.sleep', new_callable=AsyncMock)
    async def test_watch_subscription_calls_callback(self, mock_sleep):
        # Mock exchange and watch method
        mock_exchange = MagicMock()
        mock_exchange.watch_ticker = AsyncMock()
        mock_exchange.watch_ticker.side_effect = [
            {'symbol': 'BTC/USDT', 'last': 50000},
            asyncio.CancelledError()
        ]
        self.service._exchange = mock_exchange

        # Setup subscription
        sub_data = MagicMock()
        sub_data.payload = {'type': 'ticker', 'symbol': 'BTC/USDT'}
        sub_data.visibility = SubscriptionVisibility.PUBLIC

        # Setup callback
        callback = MagicMock()
        self.service._callback = callback
        self.service._is_running = True

        # Run _watch_subscription task
        # We'll use a side effect to stop the loop
        async def stop_after_call(*args, **kwargs):
            self.service._is_running = False
            return {'symbol': 'BTC/USDT', 'last': 50000}

        mock_exchange.watch_ticker.side_effect = stop_after_call

        await self.service._watch_subscription(sub_data)

        expected_wrapped_data = {
            'type': 'ticker',
            'symbol': 'BTC/USDT',
            'data': {'symbol': 'BTC/USDT', 'last': 50000}
        }
        callback.assert_called_once_with("CCXT_BINANCE", SubscriptionVisibility.PUBLIC, expected_wrapped_data)

    def test_unsubscribe(self):
        self.service._tasks['ticker_BTC/USDT'] = MagicMock()
        self.service._subscriptions['ticker_BTC/USDT'] = MagicMock()

        mock_builder = MagicMock(spec=ExchangeWebSocketBuilder)
        mock_builder.get_subscription_data.return_value = MagicMock(
            payload={'type': 'ticker', 'symbol': 'BTC/USDT'}
        )

        self.service.unsubscribe(mock_builder)

        self.assertNotIn('ticker_BTC/USDT', self.service._tasks)
        self.assertNotIn('ticker_BTC/USDT', self.service._subscriptions)


if __name__ == '__main__':
    unittest.main()
