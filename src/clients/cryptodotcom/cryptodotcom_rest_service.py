from src.clients.cryptodotcom.cryptodotcom_rest_builder import CryptoDotComRestBuilder
from src.configuration.exchanges_config import ExchangesConfig
from src.core.managers.exchange_rest_manager import ExchangeProvidersEnum
from src.core.interfaces.exchange_rest_service import ExchangeRestService, R
from src.trading.helpers.request_helper import RequestHelper


class CryptoDotComRestService(ExchangeRestService):

    def __init__(self):
        config = ExchangesConfig()
        self._base_url = config.crypto_dot_com.rest_endpoint
        self._api_key = config.crypto_dot_com.api_key
        self._secret_key = config.crypto_dot_com.secret_key

    def get_provider_name(self) -> str:
        return ExchangeProvidersEnum.CRYPTO_DOT_COM.name

    def execute(self, builder: CryptoDotComRestBuilder) -> R:
        if self._api_key and self._secret_key:
            builder.sign(self._api_key, self._secret_key)

            request = builder.build_request(self._base_url)
            response_data = RequestHelper.execute_request(request)
            mapper = builder.mapper()
            return mapper.map(response_data) if mapper else response_data

        raise ValueError("Invalid builder type for CryptoDotComRestService")

    def builder(self) -> CryptoDotComRestBuilder:
        return CryptoDotComRestBuilder()
