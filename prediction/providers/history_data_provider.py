import abc
from datetime import datetime
from typing import Optional

from pandas import DataFrame


class HistoryDataProvider(abc.ABC):
    @abc.abstractmethod
    def get_ticker_data(
        self,
        ticker_symbol: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> DataFrame:
        raise NotImplementedError()
