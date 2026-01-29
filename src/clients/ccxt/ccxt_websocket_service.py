import asyncio
import threading
from typing import Callable, ClassVar, Optional

import ccxt.pro as ccxtpro

from src.clients.ccxt.ccxt_websocket_builder import CCXTExchangeWebSocketBuilder
from src.configuration.environment_config import EnvironmentConfig
from src.core.interfaces.auth_handler import AuthHandler
from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.subscription_data import SubscriptionData, SubscriptionVisibility
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.core.managers.exchange_rest_manager import ExchangeProvidersEnum


class CCXTExchangeWebSocketService(ExchangeWebSocketService, ApplicationLoggingMixin):
    _SUPPORTED_PROVIDERS: ClassVar[set[ExchangeProvidersEnum]] = {
        ExchangeProvidersEnum.CCXT_BINANCE,
        ExchangeProvidersEnum.CCXT_KRAKEN,
        ExchangeProvidersEnum.CCXT_COINBASE,
        ExchangeProvidersEnum.CCXT_BYBIT,
        ExchangeProvidersEnum.CCXT_KUCOIN,
    }

    _MAP: ClassVar[dict[ExchangeProvidersEnum, str]] = {
        ExchangeProvidersEnum.CCXT_BINANCE: "binance",
        ExchangeProvidersEnum.CCXT_KRAKEN: "kraken",
        ExchangeProvidersEnum.CCXT_COINBASE: "coinbase",
        ExchangeProvidersEnum.CCXT_BYBIT: "bybit",
        ExchangeProvidersEnum.CCXT_KUCOIN: "kucoin",
    }

    def __init__(self, provider: ExchangeProvidersEnum):
        self._provider: ExchangeProvidersEnum = provider
        self._exchange: Optional[ccxtpro.Exchange] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._tasks: dict[str, asyncio.Task] = {}
        self._subscriptions: dict[str, SubscriptionData] = {}
        self._callback: Optional[Callable[[str, SubscriptionVisibility, dict], None]] = None
        self._is_running: bool = False

    def get_provider_name(self) -> str:
        return self._provider.value

    @classmethod
    def get_supported_providers(cls) -> set[ExchangeProvidersEnum]:
        return cls._SUPPORTED_PROVIDERS

    def get_websocket_url(self, visibility: SubscriptionVisibility) -> str:
        # We use a marker URL to signal to WebSocketManager that this is a managed connection
        return f"ccxt://{self._provider.value}/{visibility.value}"

    def get_auth_request(self) -> dict:
        return {}  # CCXT Pro handles auth internally

    def get_auth_handler(self) -> Optional[AuthHandler]:
        return None

    def get_heartbeat_handler(self) -> Optional[HeartbeatHandler]:
        return None

    def builder(self) -> ExchangeWebSocketBuilder:
        return CCXTExchangeWebSocketBuilder(self.get_provider_name())

    def connect(self, callback: Callable[[str, SubscriptionVisibility, dict], None]) -> None:
        if self._is_running:
            return

        self._callback = callback
        self._is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name=f"CCXT-WS-{self._provider.value}")
        self._thread.start()
        self.app_logger.info(f"Started CCXT WebSocket connection for {self.get_provider_name()}")

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            __p = self._MAP.get(self._provider) or ""
            exchange_class = getattr(ccxtpro, __p)
            config = EnvironmentConfig()
            credentials = config.ccxt_providers.get_provider_credentials(__p)  # pylint: disable=no-member

            self._exchange = exchange_class({
                'apiKey': credentials.api_key if credentials else None,
                'secret': credentials.secret_key.get_secret_value() if credentials and credentials.secret_key else None,
                'enableRateLimit': True,
            })

            # Run until self._is_running is False
            self._loop.run_until_complete(self._wait_for_shutdown())
        except Exception as e:
            self.app_logger.error(f"CCXT WebSocket loop error for {self._provider.value}: {e}")
        finally:
            if self._exchange:
                self._loop.run_until_complete(self._exchange.close())
            self._loop.close()

    async def _wait_for_shutdown(self):
        while self._is_running:
            await asyncio.sleep(1)

    async def _watch_subscription(self, sub: SubscriptionData):
        payload = sub.payload
        sub_type = payload['type']
        symbol = payload['symbol']

        provider_name = self.get_provider_name()

        while self._is_running:
            try:
                data = None
                if sub_type == 'ticker':
                    data = await self._exchange.watch_ticker(symbol)
                elif sub_type == 'ohlcv':
                    timeframe = payload['timeframe']
                    data = await self._exchange.watch_ohlcv(symbol, timeframe)
                elif sub_type == 'balance':
                    data = await self._exchange.watch_balance()
                elif sub_type == 'orders':
                    data = await self._exchange.watch_orders(symbol)

                if data and self._callback:
                    # Pass wrapped data to the central callback to ensure proper matching
                    wrapped_data = {
                        'type': sub_type,
                        'symbol': symbol,
                        'data': data
                    }
                    self._callback(provider_name, sub.visibility, wrapped_data)

            except Exception as e:
                self.app_logger.error(f"CCXT Watch error for {self._provider.value} {sub_type} {symbol}: {e}")
                await asyncio.sleep(5)

    def subscribe(self, builder: ExchangeWebSocketBuilder) -> None:
        sub_data = builder.get_subscription_data()
        payload = sub_data.payload
        sub_id = f"{payload['type']}_{payload['symbol']}"
        if payload.get('timeframe'):
            sub_id += f"_{payload['timeframe']}"

        if sub_id not in self._subscriptions:
            self._subscriptions[sub_id] = sub_data
            self.app_logger.info(
                f"Subscribing to {payload['type']} for {payload.get('symbol', 'N/A')} on {self.get_provider_name()}"
            )
            if self._loop and self._loop.is_running():
                task = asyncio.run_coroutine_threadsafe(self._watch_subscription(sub_data), self._loop)
                self._tasks[sub_id] = task

    def unsubscribe(self, builder: ExchangeWebSocketBuilder) -> None:
        sub_data = builder.get_subscription_data()
        payload = sub_data.payload
        sub_id = f"{payload['type']}_{payload['symbol']}"
        if payload.get('timeframe'):
            sub_id += f"_{payload['timeframe']}"

        if sub_id in self._tasks:
            self._tasks[sub_id].cancel()
            del self._tasks[sub_id]
        if sub_id in self._subscriptions:
            del self._subscriptions[sub_id]
            self.app_logger.info(
                f"Unsubscribed from {payload['type']} for {payload.get('symbol', 'N/A')} on {self.get_provider_name()}"
            )
