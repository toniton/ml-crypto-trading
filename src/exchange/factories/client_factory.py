from typing import Optional

from src.exchange.managers.rest_manager import RestManager
from src.exchange.managers.websocket_manager import WebSocketManager
from src.metrics.collectors.exchange_metrics_collector import ExchangeMetricsCollector
from src.simulation.simulated_account import SimulatedAccount
from src.simulation.simulated_rest_manager import SimulatedRestManager
from src.simulation.simulated_websocket_manager import SimulatedWebSocketManager


class ClientFactory:
    @staticmethod
    def create_rest_manager(
            is_simulated: bool,
            metrics_collector: Optional[ExchangeMetricsCollector] = None,
    ) -> RestManager:
        if is_simulated:
            return ClientFactory._create_simulated_rest_manager(metrics_collector)
        return RestManager(metrics_collector=metrics_collector)

    @staticmethod
    def create_websocket_manager(
            is_simulated: bool,
            metrics_collector: Optional[ExchangeMetricsCollector] = None,
    ) -> WebSocketManager:
        if is_simulated:
            return ClientFactory._create_simulated_websocket_manager(metrics_collector)
        return WebSocketManager(metrics_collector=metrics_collector)

    @staticmethod
    def _create_simulated_rest_manager(
            metrics_collector: Optional[ExchangeMetricsCollector] = None,
    ) -> SimulatedRestManager:
        simulated_account = SimulatedAccount()
        return SimulatedRestManager(simulated_account, metrics_collector=metrics_collector)

    @staticmethod
    def _create_simulated_websocket_manager(
            metrics_collector: Optional[ExchangeMetricsCollector] = None,
    ) -> SimulatedWebSocketManager:
        return SimulatedWebSocketManager(metrics_collector=metrics_collector)

