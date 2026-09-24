from typing import ClassVar

import ccxt

from src.configuration.environment_config import EnvironmentConfig
from src.core.interfaces.exchange_rest_service import ExchangeRestService, R
from src.exchange.clients.ccxt.ccxt_rest_builder import CCXTEndpoint, CCXTExchangeRestBuilder
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum


class CCXTExchangeRestService(ExchangeRestService):
    _SUPPORTED_PROVIDERS: ClassVar[set[ExchangeProvidersEnum]] = {
        ExchangeProvidersEnum.CCXT_BINANCE,
        ExchangeProvidersEnum.CCXT_KRAKEN,
        ExchangeProvidersEnum.CCXT_COINBASE,
        ExchangeProvidersEnum.CCXT_BYBIT,
        ExchangeProvidersEnum.CCXT_KUCOIN,
    }

    _CLASS_MAP: ClassVar[dict[ExchangeProvidersEnum, type]] = {
        ExchangeProvidersEnum.CCXT_BINANCE: ccxt.binance,
        ExchangeProvidersEnum.CCXT_KRAKEN: ccxt.kraken,
        ExchangeProvidersEnum.CCXT_COINBASE: ccxt.coinbase,
        ExchangeProvidersEnum.CCXT_BYBIT: ccxt.bybit,
        ExchangeProvidersEnum.CCXT_KUCOIN: ccxt.kucoin,
    }

    def __init__(self, provider: ExchangeProvidersEnum):
        self._provider = provider
        exchange_class = self._CLASS_MAP.get(provider)
        if exchange_class is None:
            raise ValueError(f"CCXT does not support exchange: {provider}")
        try:
            config = EnvironmentConfig()
            credentials = config.ccxt_providers.get_provider_credentials(provider)

            self._exchange = exchange_class({
                'apiKey': credentials.api_key if credentials else None,
                'secret': credentials.secret_key.get_secret_value() if credentials and credentials.secret_key else None,
                'enableRateLimit': True,
                'options': {'fetchOpenOrders': {'warnWithoutSymbol': False}},
            })
        except AttributeError as exc:
            raise ValueError(f"CCXT does not support exchange: {provider}") from exc
        except ImportError as exc:
            raise ImportError("ccxt library not installed. Install with: pip install ccxt") from exc

    def get_provider_name(self) -> str:
        return self._provider.value

    @classmethod
    def get_supported_providers(cls) -> set[ExchangeProvidersEnum]:
        return cls._SUPPORTED_PROVIDERS

    def execute(self, builder: CCXTExchangeRestBuilder) -> R:
        endpoint = builder.get_endpoint()
        if not endpoint or not isinstance(endpoint, CCXTEndpoint):
            raise ValueError("Invalid builder for CCXTExchangeRestService")

        method_map = {
            "fetch_ticker": self._exchange.fetch_ticker,
            "fetch_order_book": self._exchange.fetch_order_book,
            "fetch_ohlcv": self._exchange.fetch_ohlcv,
            "fetch_balance": self._exchange.fetch_balance,
            "fetch_trading_fees": self._exchange.fetch_trading_fees,
            "fetch_trading_fee": self._exchange.fetch_trading_fee,
            "create_order": self._exchange.create_order,
            "fetch_order": self._exchange.fetch_order,
            "fetch_open_orders": self._exchange.fetch_open_orders,
            "cancel_order": self._exchange.cancel_order,
        }
        method = method_map.get(endpoint.method_name)
        if method is None or not callable(method):
            raise ValueError(f"Exchange does not support method: {endpoint.method_name}")
        response = method(**endpoint.params)

        # Mapping logic
        mapper = builder.mapper()
        if mapper:
            return mapper.map(response)

        return response

    def builder(self) -> CCXTExchangeRestBuilder:
        return CCXTExchangeRestBuilder(self.get_provider_name())
