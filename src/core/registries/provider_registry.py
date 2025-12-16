from abc import ABC

from src.core.interfaces.exchange_rest_client import ExchangeRestClient


class  ProviderRegistry(ABC):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.providers: dict[str, ExchangeRestClient] = {}

    def register_provider(self, provider: ExchangeRestClient):
        if provider.get_provider_name() in self.providers:
            raise ValueError(f"Provider ${provider.get_provider_name()} already registered.")
        self.providers[provider.get_provider_name()] = provider

    def get_provider(self, provider_name: str) -> ExchangeRestClient:
        provider = self.providers.get(provider_name)
        if provider is None:
            raise ValueError(f"Provider {provider_name} not registered.")
        return provider
