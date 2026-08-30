from api.interfaces.order import Order

from src.backtest.execution.latency.latency_model import LatencyModel


class FixedLatencyModel(LatencyModel):
    def __init__(self, milliseconds: float = 500.0):
        self._latency_seconds = milliseconds / 1000.0

    def get_latency(self, _order: Order, _ticker_symbol: str) -> float:
        return self._latency_seconds
