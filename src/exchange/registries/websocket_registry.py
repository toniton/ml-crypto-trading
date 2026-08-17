from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.registry import Registry


class WebSocketRegistry(Registry[str, ExchangeWebSocketService]):
    def register_service(self, service: ExchangeWebSocketService):
        self.register(service.get_provider_name(), service)

    def get_service(self, provider_name: str) -> ExchangeWebSocketService:
        return self.get(provider_name)

    def get_registered_services(self):
        return self.keys()
