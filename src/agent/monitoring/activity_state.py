from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass
class AssetActivityState:
    ticker_symbol: str
    last_market_data_at: Optional[float] = None
    last_evaluation_at: Optional[float] = None
    last_signal_at: Optional[float] = None
    last_order_at: Optional[float] = None
    last_execution_at: Optional[float] = None

    @property
    def last_activity_at(self) -> Optional[float]:
        present = [
            value for value in (
                self.last_market_data_at,
                self.last_evaluation_at,
                self.last_signal_at,
                self.last_order_at,
                self.last_execution_at,
            ) if value is not None
        ]
        return max(present) if present else None

    def to_dict(self) -> dict:
        return {
            "ticker_symbol": self.ticker_symbol,
            "last_market_data_at": self.last_market_data_at,
            "last_evaluation_at": self.last_evaluation_at,
            "last_signal_at": self.last_signal_at,
            "last_order_at": self.last_order_at,
            "last_execution_at": self.last_execution_at,
        }


@runtime_checkable
class ActivityStateProvider(Protocol):
    @property
    def started_at(self) -> float:
        ...

    def state_for(self, ticker_symbol: str) -> Optional[AssetActivityState]:
        ...

    def states(self) -> list[AssetActivityState]:
        ...