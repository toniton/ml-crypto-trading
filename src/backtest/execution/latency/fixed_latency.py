from api.interfaces.order import Order


class FixedLatencyModel:
    def __init__(self, milliseconds: float = 500.0):
        self._latency_seconds = milliseconds / 1000.0

    def get_latency(self, _order: Order, _ticker_symbol: str) -> float:
        return self._latency_seconds
