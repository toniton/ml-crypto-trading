from decimal import Decimal
from typing import Any, List
from urllib.error import HTTPError

from cachetools import cached, TTLCache
from circuitbreaker import circuit

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.core.managers.exchange_rest_manager import ExchangeRestManager
from src.core.registries.rest_registry import RestRegistry


class RestManager(ExchangeRestManager, RestRegistry):
    def __init__(self):
        super().__init__()

    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_market_data(self, exchange: str, ticker_symbol: str) -> MarketData:
        service = self.get_service(exchange)
        builder = service.builder().market_data(ticker_symbol)
        return service.execute(builder)

    @cached(cache=TTLCache(maxsize=1024, ttl=600))
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_account_balance(self, exchange: str) -> List[AccountBalance]:
        service = self.get_service(exchange)
        builder = service.builder().account_balance()
        return service.execute(builder)

    @cached(cache=TTLCache(maxsize=1024, ttl=6000))
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_account_fees(self, exchange: str) -> Fees:
        service = self.get_service(exchange)
        builder = service.builder().account_fees()
        return service.execute(builder)

    @cached(cache=TTLCache(maxsize=1024, ttl=6000))
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_instrument_fees(self, exchange: str, ticker_symbol: str) -> Fees:
        service = self.get_service(exchange)
        builder = service.builder().instrument_fees(ticker_symbol)
        return service.execute(builder)

    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_order(self, exchange: str, uuid: str) -> Any:
        service = self.get_service(exchange)
        builder = service.builder().get_order(uuid)
        return service.execute(builder)

    def place_order(
            self,
            exchange: str,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: Decimal,
            trade_action: TradeAction
    ) -> None:
        service = self.get_service(exchange)
        builder = service.builder().create_order(
            uuid, ticker_symbol, quantity, price, trade_action
        )
        service.execute(builder)

    def cancel_order(self, exchange: str, uuid: str) -> None:
        service = self.get_service(exchange)
        builder = service.builder().cancel_order(uuid)
        service.execute(builder)

    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_candles(self, exchange: str, ticker_symbol: str, timeframe: Timeframe) -> List[Candle]:
        service = self.get_service(exchange)
        builder = service.builder().candles(ticker_symbol, timeframe)
        return service.execute(builder)
