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
            f"audit-{base_name}",
            f"audit-{base_name.lower()}",
            f"audit-{base_name.upper()}",
            f"audit-{base_name.replace('-', '_')}",
            f"audit-{base_name.replace('-', '_').lower()}",
            f"audit-{base_name.replace('-', '_').upper()}",
        }
        potential_filenames = []
        for f in potential_names:
            potential_filenames.append(f"{f}.csv")
            potential_filenames.append(f"{f}.log")
            # Support for dated audit logs like audit-BTC_USD-2026-01.log
            # We can use glob to find these if we want, but let's stick to a few more patterns
            potential_filenames.append(f"{f}-*.log")
            potential_filenames.append(f"{f}*.log")
            potential_filenames.append(f"{f}*.csv")

        import glob
        file_path = None
        for pattern in potential_filenames:
            candidate_pattern = os.path.join(self.data_path, pattern)
            matches = glob.glob(candidate_pattern)
            if matches:
                file_path = matches[0]
                break

        if not file_path:
            raise FileNotFoundError(
                f"Historical data file not found for {ticker_symbol} in {self.data_path}. "
                f"Tried: {', '.join(potential_filenames)}"
            )

        # Detect separator and format
        first_line = ""
        with open(file_path, "r") as f:
            first_line = f.readline()

        if "event_type" in first_line:
            # Audit log format
            df = pd.read_csv(file_path, sep=",")
            data_points = []
            for _, row in df.iterrows():
                # Filter by ticker symbol if it's the global audit log
                if "asset" in row and row["asset"] != ticker_symbol.replace("/", "_"):
                    continue

                # We only care about events that have market data
                if pd.isna(row["close_price"]):
                    continue

                data_point = HistoricalDataPoint(
                    timestamp=int(row["timestamp"]) // 1000,  # Audit log uses ms
                    open_price=Decimal(str(row["close_price"])),  # Audit log doesn't have open, use close
                    high_price=Decimal(str(row["high_price"])),
                    low_price=Decimal(str(row["low_price"])),
                    close_price=Decimal(str(row["close_price"])),
                    volume=Decimal(str(row["volume"])),
                    market_cap=Decimal("0")
                )
                data_points.append(data_point)
        else:
            # Historical data format
            try:
                df = pd.read_csv(file_path, sep=";")
                if len(df.columns) < 2:
                    raise ValueError("Separator detection failed")
            except (ValueError, KeyError):
                df = pd.read_csv(file_path, sep=",")

            data_points = []
            for _, row in df.iterrows():
                try:
                    ts_val = row["timestamp"]
                    if isinstance(ts_val, (int, float)):
                        timestamp = int(ts_val)
                    else:
                        timestamp = int(pd.Timestamp(ts_val).timestamp())

                    data_point = HistoricalDataPoint(
                        timestamp=timestamp,
                        open_price=Decimal(str(row["open"])),
                        high_price=Decimal(str(row["high"])),
                        low_price=Decimal(str(row["low"])),
                        close_price=Decimal(str(row["close"])),
                        volume=Decimal(str(row["volume"])),
                        market_cap=Decimal(str(row.get("marketCap", 0)))
                    )
                    data_points.append(data_point)
                except Exception:
                    continue

        data_points.sort(key=lambda x: x.timestamp)

        self._data_index[ticker_symbol] = {dp.timestamp: dp for dp in data_points}

        return data_points

    def get_data(self, ticker_symbol: str, timestamp: int) -> HistoricalDataPoint | None:
        if ticker_symbol in self._data_index:
            return self._data_index[ticker_symbol].get(timestamp)
        return None
