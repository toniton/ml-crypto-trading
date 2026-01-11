from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import List

import pandas as pd


@dataclass
class HistoricalDataPoint:
    timestamp: int
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    market_cap: Decimal


class BacktestDataLoader:
    def __init__(self, data_path: str):
        self._data_index = {}
        self.data_path = data_path

    def load(self, ticker_symbol: str) -> List[HistoricalDataPoint]:
        base_name = ticker_symbol.replace("/", "_")
        potential_names = {
            base_name,
            base_name.lower(),
            base_name.upper(),
            base_name.replace("_", "-"),
            base_name.replace("_", "-").lower(),
            base_name.replace("_", "-").upper(),
            base_name.replace("-", "_"),
            base_name.replace("-", "_").lower(),
            base_name.replace("-", "_").upper(),
        }
        potential_filenames = [f"{f}.csv" for f in potential_names]

        file_path = None
        for filename in potential_filenames:
            candidate_path = os.path.join(self.data_path, filename)
            if os.path.exists(candidate_path):
                file_path = candidate_path
                break

        if not file_path:
            raise FileNotFoundError(
                f"Historical data file not found for {ticker_symbol} in {self.data_path}. "
                f"Tried: {', '.join(potential_filenames)}"
            )

        # Detect separator - try both ; and ,
        try:
            df = pd.read_csv(file_path, sep=";")
            if len(df.columns) < 2:
                raise ValueError("Separator detection failed")
        except ValueError:
            df = pd.read_csv(file_path, sep=",")

        data_points = []
        for _, row in df.iterrows():
            timestamp = int(pd.Timestamp(row["timestamp"]).timestamp())
            data_point = HistoricalDataPoint(
                timestamp=timestamp,
                open_price=Decimal(str(row["open"])),
                high_price=Decimal(str(row["high"])),
                low_price=Decimal(str(row["low"])),
                close_price=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
                market_cap=Decimal(str(row["marketCap"]))
            )
            data_points.append(data_point)

        data_points.sort(key=lambda x: x.timestamp)

        self._data_index[ticker_symbol] = {dp.timestamp: dp for dp in data_points}

        return data_points

    def get_data(self, ticker_symbol: str, timestamp: int) -> HistoricalDataPoint | None:
        if ticker_symbol in self._data_index:
            return self._data_index[ticker_symbol].get(timestamp)
        return None
