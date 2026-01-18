from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.registry import Registry


class WebSocketRegistry(Registry[str, ExchangeWebSocketService]):
    def register_service(self, service: ExchangeWebSocketService):
        self._register(service.get_provider_name(), service)

    def get_service(self, provider_name: str) -> ExchangeWebSocketService:
        return self._get_first(provider_name)

    def get_registered_services(self):
        return self._keys()
