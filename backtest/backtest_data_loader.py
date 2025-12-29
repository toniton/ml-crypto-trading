from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

import pandas as pd


@dataclass
class HistoricalDataPoint:
    timestamp: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    market_cap: float


class BacktestDataLoader:
    def __init__(self, data_path: str):
        self._data_index = {}
        self.data_path = data_path

    def load(self, ticker_symbol: str, use_mini: bool = False) -> List[HistoricalDataPoint]:
        suffix = "-test-mini" if use_mini else ""
        filename = f"{ticker_symbol.lower()}{suffix}.csv"
        file_path = os.path.join(self.data_path, filename)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Historical data file not found: {file_path}")

        df = pd.read_csv(file_path, sep=";")

        data_points = []
        for _, row in df.iterrows():
            timestamp = int(pd.Timestamp(row["timestamp"]).timestamp())
            data_point = HistoricalDataPoint(
                timestamp=timestamp,
                open_price=float(row["open"]),
                high_price=float(row["high"]),
                low_price=float(row["low"]),
                close_price=float(row["close"]),
                volume=float(row["volume"]),
                market_cap=float(row["marketCap"])
            )
            data_points.append(data_point)

        data_points.sort(key=lambda x: x.timestamp)

        self._data_index[ticker_symbol] = {dp.timestamp: dp for dp in data_points}

        return data_points

    def get_data(self, ticker_symbol: str, timestamp: int) -> HistoricalDataPoint | None:
        if ticker_symbol in self._data_index:
            return self._data_index[ticker_symbol].get(timestamp)
        return None
