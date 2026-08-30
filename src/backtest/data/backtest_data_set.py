from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.backtest.backtest_data_loader import HistoricalDataPoint


@dataclass(frozen=True)
class BacktestDataSet:
    dataset_id: str
    ticker_symbol: str
    start_time: datetime
    end_time: datetime
    data_points: tuple[HistoricalDataPoint, ...]
    _index: dict[int, HistoricalDataPoint] = field(
        default_factory=dict, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        timestamps = [data_point.timestamp for data_point in self.data_points]
        if timestamps != sorted(timestamps):
            raise ValueError(
                f"Dataset {self.dataset_id} data points are not ordered by timestamp."
            )
        if len(timestamps) != len(set(timestamps)):
            raise ValueError(
                f"Dataset {self.dataset_id} contains duplicate timestamps."
            )
        object.__setattr__(
            self, "_index", {data_point.timestamp: data_point for data_point in self.data_points}
        )

    @property
    def timestamps(self) -> tuple[int, ...]:
        return tuple(data_point.timestamp for data_point in self.data_points)

    def get(self, timestamp: int) -> Optional[HistoricalDataPoint]:
        return self._index.get(timestamp)

    def __len__(self) -> int:
        return len(self.data_points)
