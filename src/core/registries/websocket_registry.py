from abc import ABC

from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder


class  WebSocketRegistry(ABC):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.websockets: dict[str, ExchangeWebSocketBuilder] = {}

    def register_websocket(self, websocket_client: ExchangeWebSocketBuilder):
        provider_name = websocket_client.get_provider_name()
        if provider_name in iter(self.websockets):
            raise ValueError(f"Provider ${provider_name} already registered.")
        self.websockets[provider_name] = websocket_client

    def get_websocket(self, provider_name: str) -> ExchangeWebSocketBuilder:
        websocket = self.websockets.get(provider_name)
        if websocket is None:
            raise ValueError(f"Provider {provider_name} not registered.")
        return websocket
