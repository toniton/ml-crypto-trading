import abc
from datetime import datetime

from api.interfaces.order import Order
from src.database.repositories.base_repository import BaseRepository


class OrderRepository(BaseRepository[Order]):

    @abc.abstractmethod
    def get_by_exchange(self, exchange_name: str):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_by_ticker_symbol(self, ticker_symbol: str):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_by_date(self, date):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_by_date_range(self, start: datetime, end: datetime) -> list[Order]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_by_status(self, status: str):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_non_terminal(self) -> list[Order]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_by_price(self, ticker_symbol: str, price: str):
        raise NotImplementedError()
