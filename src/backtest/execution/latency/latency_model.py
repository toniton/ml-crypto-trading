from typing import Protocol

from api.interfaces.order import Order


class LatencyModel(Protocol):
    def get_latency(self, order: Order, ticker_symbol: str) -> float:
        ...
