from src.core.interfaces.exchange_rest_service import ExchangeRestService
from src.core.interfaces.registry import Registry


class RestRegistry(Registry[str, ExchangeRestService]):
    def register_service(self, provider: ExchangeRestService):
        self._register(provider.get_provider_name(), provider)

    def get_service(self, provider_name: str) -> ExchangeRestService:
        return self._get_first(provider_name)

    def get_registered_services(self):
        return self._keys()
