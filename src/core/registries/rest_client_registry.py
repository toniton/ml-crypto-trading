from abc import ABC

from src.core.interfaces.exchange_rest_client import ExchangeRestClient


class RestClientRegistry(ABC):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rest_clients: dict[str, ExchangeRestClient] = {}

    def register_client(self, provider: ExchangeRestClient):
        if provider.get_provider_name() in self.rest_clients:
            raise ValueError(f"Provider ${provider.get_provider_name()} already registered.")
        self.rest_clients[provider.get_provider_name()] = provider

    def get_client(self, provider_name: str) -> ExchangeRestClient:
        provider = self.rest_clients.get(provider_name)
        if provider is None:
            raise ValueError(f"Provider {provider_name} not registered.")
        return provider
