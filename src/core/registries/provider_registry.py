from abc import ABC

from api.interfaces.exchange_provider import ExchangeProvider


class ProviderRegistry(ABC):

    def __init__(self):
        self.providers: dict[str, ExchangeProvider] = {}

    def register_provider(self, provider: ExchangeProvider):
        if provider.get_provider_name() in self.providers:
            raise ValueError(f"Provider ${provider.get_provider_name()} already registered.")
        self.providers[provider.get_provider_name()] = provider

    def get_provider(self, provider_name: str) -> ExchangeProvider:
        provider = self.providers.get(provider_name)
        if provider is None:
            raise Exception(f"Provider $provider not supported.")
        return provider
