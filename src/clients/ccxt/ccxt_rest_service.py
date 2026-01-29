from typing import ClassVar

import ccxt

from src.clients.ccxt.ccxt_rest_builder import CCXTEndpoint, CCXTExchangeRestBuilder
from src.configuration.environment_config import EnvironmentConfig
from src.core.interfaces.exchange_rest_service import ExchangeRestService, R
from src.core.managers.exchange_rest_manager import ExchangeProvidersEnum


class CCXTExchangeRestService(ExchangeRestService):
    _SUPPORTED_PROVIDERS: ClassVar[set[str]] = {
        ExchangeProvidersEnum.CCXT_BINANCE.value,
        # 'kraken',
        # 'coinbase',
        # 'bybit',
        # 'kucoin',
    }

    _MAP = {
        ExchangeProvidersEnum.CCXT_BINANCE.value: "binance"
    }

    def __init__(self, provider: str):
        self._provider = provider
        __p = self._MAP.get(provider) or ""
        try:
            exchange_class = getattr(ccxt, __p)
            config = EnvironmentConfig()
            credentials = config.ccxt_providers.get_provider_credentials(__p)

            self._exchange = exchange_class({
                'apiKey': credentials.api_key if credentials else None,
                'secret': credentials.secret_key.get_secret_value() if credentials and credentials.secret_key else None,
                'enableRateLimit': True,
            })
        except AttributeError as exc:
            raise ValueError(f"CCXT does not support exchange: {__p}") from exc
        except ImportError as exc:
            raise ImportError("ccxt library not installed. Install with: pip install ccxt") from exc

    def get_provider_name(self) -> str:
        return self._provider.upper()

    @classmethod
    def get_supported_providers(cls) -> set[str]:
        return cls._SUPPORTED_PROVIDERS

    def execute(self, builder: CCXTExchangeRestBuilder) -> R:
        endpoint = builder.get_endpoint()
        if not endpoint or not isinstance(endpoint, CCXTEndpoint):
            raise ValueError("Invalid builder for CCXTExchangeRestService")

        method = getattr(self._exchange, endpoint.method_name)
        response = method(**endpoint.params)

        # Mapping logic
        mapper = builder.mapper()
        if mapper:
            return mapper.map(response)

        return response

    def builder(self) -> CCXTExchangeRestBuilder:
        return CCXTExchangeRestBuilder(self.get_provider_name())
