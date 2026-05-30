from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional, TypeVar

from pydantic import BaseModel

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.timeframe import Timeframe
from src.clients.ccxt.ccxt_mapper import CCXTMapperFactory, CCXTTimeframe
from src.core.interfaces.exchange_rest_builder import Endpoint, ExchangeRestBuilder
from src.core.interfaces.mapper import Mapper

T = TypeVar('T', bound=BaseModel)
R = TypeVar('R')


@dataclass(frozen=True)
class CCXTEndpoint(Endpoint):
    method_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)


class CCXTExchangeRestBuilder(ExchangeRestBuilder[T, R]):
    def __init__(self, provider_name: str = ""):
        super().__init__()
        self._provider_name = provider_name
        self._method_name: Optional[str] = None
        self._params: dict[str, Any] = {}
        self._endpoint: Optional[CCXTEndpoint] = None

    def mapper(self) -> Optional[Mapper]:
        return self._mapper

    def market_data(self, ticker_symbol: str) -> 'CCXTExchangeRestBuilder[T, MarketData]':
        self._method_name = 'fetch_ticker'
        self._params = {'symbol': ticker_symbol}
        self._mapper = CCXTMapperFactory.get_mapper('ticker')
        return self

    def candles(self, ticker_symbol: str, timeframe: Timeframe) -> 'CCXTExchangeRestBuilder[T, list[Candle]]':
        self._method_name = 'fetch_ohlcv'
        self._params = {
            'symbol': ticker_symbol,
            'timeframe': CCXTTimeframe.MAP.get(timeframe),
            'limit': 50
        }
        self._mapper = CCXTMapperFactory.get_mapper('ohlcv')
        return self

    def account_balance(self) -> 'CCXTExchangeRestBuilder[T, list[AccountBalance]]':
        self._method_name = 'fetch_balance'
        self._params = {}
        self._mapper = CCXTMapperFactory.get_mapper('balance')
        return self

    def account_fees(self) -> 'CCXTExchangeRestBuilder[T, Fees | None]':
        self._method_name = 'fetch_trading_fees'
        self._params = {}
        self._mapper = CCXTMapperFactory.get_mapper('fees')
        return self

    def instrument_fees(self, ticker_symbol: str) -> 'CCXTExchangeRestBuilder[T, Fees]':
        self._method_name = 'fetch_trading_fee'
        self._params = {'symbol': ticker_symbol}
        self._mapper = CCXTMapperFactory.get_mapper('fees')
        return self

    def create_order(
            self,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: Decimal,
            trade_action
    ) -> 'CCXTExchangeRestBuilder[T, None]':
        self._method_name = 'create_order'
        self._params = {
            'symbol': ticker_symbol,
            'type': 'limit',
            'side': trade_action.value.lower(),
            'amount': float(quantity),
            'price': float(price),
            'params': {'clientOrderId': uuid}
        }
        self._mapper = CCXTMapperFactory.get_mapper('orders', self._provider_name)
        return self

    def get_order(self, uuid: str) -> 'CCXTExchangeRestBuilder[T, Order]':
        self._method_name = 'fetch_order'
        self._params = {'id': uuid}
        self._mapper = CCXTMapperFactory.get_mapper('orders', self._provider_name)
        return self

    def cancel_order(self, uuid: str) -> 'CCXTExchangeRestBuilder[T, None]':
        self._method_name = 'cancel_order'
        self._params = {'id': uuid}
        self._mapper = None
        return self

    def get_endpoint(self) -> Optional[CCXTEndpoint]:
        if not self._method_name:
            return None
        return CCXTEndpoint(
            path=self._method_name,  # We use path to store method name for CCXT
            private=True,  # Most CCXT calls we use are authenticated/impact account
            method_name=self._method_name,
            params=self._params,
            mapper=self._mapper
        )

    def get_params(self) -> dict:
        return self._params
