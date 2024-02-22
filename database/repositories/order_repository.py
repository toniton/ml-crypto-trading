import abc

from database.repositories.base_repository import BaseRepository


class OrderRepository(BaseRepository):

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
    def get_by_status(self, status: str):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_by_price(self, ticker_symbol: str, price: str):
        raise NotImplementedError()
