from __future__ import annotations

from src.clients.rest_manager import RestManager
from src.clients.websocket_manager import WebSocketManager
from src.core.simulation.simulated_account import SimulatedAccount
from src.core.simulation.simulated_rest_manager import SimulatedRestManager
from src.core.simulation.simulated_websocket_manager import SimulatedWebSocketManager


class ClientFactory:
    @staticmethod
    def create_rest_manager(is_simulated: bool) -> RestManager:
        if is_simulated:
            return ClientFactory._create_simulated_rest_manager()
        return RestManager()

    @staticmethod
    def create_websocket_manager(is_simulated: bool) -> WebSocketManager:
        if is_simulated:
            return ClientFactory._create_simulated_websocket_manager()
        return WebSocketManager()

    @staticmethod
    def _create_simulated_rest_manager() -> SimulatedRestManager:
        simulated_account = SimulatedAccount()
        return SimulatedRestManager(simulated_account)

    @staticmethod
    def _create_simulated_websocket_manager() -> SimulatedWebSocketManager:
        return SimulatedWebSocketManager()
