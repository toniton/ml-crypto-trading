from typing import ClassVar

from src.clients.cryptodotcom.cryptodotcom_rest_builder import CryptoDotComRestBuilder
from src.configuration.exchanges_config import ExchangesConfig
from src.core.interfaces.exchange_rest_service import ExchangeRestService, R
from src.core.managers.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.helpers.request_helper import RequestHelper


class CryptoDotComRestService(ExchangeRestService):
    _SUPPORTED_PROVIDERS: ClassVar[set[str]] = {ExchangeProvidersEnum.CRYPTO_DOT_COM.name.lower()}

    def __init__(self, provider: str = None):
        config = ExchangesConfig()
        self._provider = provider or ExchangeProvidersEnum.CRYPTO_DOT_COM.name.lower()
        self._base_url = config.crypto_dot_com.rest_endpoint
        self._api_key = config.crypto_dot_com.api_key
        self._secret_key = config.crypto_dot_com.secret_key

    @classmethod
    def get_supported_providers(cls) -> set[str]:
        return cls._SUPPORTED_PROVIDERS

    def get_provider_name(self) -> str:
        return self._provider.upper()

    def execute(self, builder: CryptoDotComRestBuilder) -> R:
        if self._api_key and self._secret_key:
            builder.sign(self._api_key, self._secret_key.get_secret_value())

            request = builder.build_request(self._base_url)
            response_data = RequestHelper.execute_request(request)
            mapper = builder.mapper()
            return mapper.map(response_data) if mapper else response_data

        raise ValueError("Invalid builder type for CryptoDotComRestService")

    def builder(self) -> CryptoDotComRestBuilder:
        return CryptoDotComRestBuilder()
