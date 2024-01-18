from datetime import datetime
from typing import Optional

from prediction.providers.history_data_provider import HistoryDataProvider


class CoinMarketCapDataProvider(HistoryDataProvider):

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key

    def get_ticker_data(
        self, ticker_symbol: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ):
        pass

    ...
