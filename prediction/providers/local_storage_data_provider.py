import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from prediction.providers.history_data_provider import HistoryDataProvider


class LocalStorageDataProvider(HistoryDataProvider):
    def __init__(self, directory: str):
        self.directory = Path(os.getcwd()).joinpath(directory)

    def get_ticker_data(
        self, ticker_symbol: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ):
        file_path = f"{self.directory}/coinmarketcap/history/{ticker_symbol.lower()}-usd.csv"

        if os.path.exists(file_path):
            history = pd.read_csv(file_path, sep=";")
            return history

        raise Exception(f"Data source for ticker: {ticker_symbol} does not exist in: {file_path}.")
