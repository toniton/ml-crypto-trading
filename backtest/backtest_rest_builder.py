from __future__ import annotations

from decimal import Decimal
from typing import Optional, TypeVar, Any
from pydantic import BaseModel

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from src.core.interfaces.exchange_rest_builder import ExchangeRestBuilder

T = TypeVar('T', bound=BaseModel)
R = TypeVar('R')


class BacktestRestBuilder(ExchangeRestBuilder[T, R]):
    def __init__(self):
        super().__init__()
        self.method_name: Optional[str] = None
        self.params: dict[str, Any] = {}

    def market_data(self, ticker_symbol: str) -> 'BacktestRestBuilder[T, MarketData]':
        self.method_name = "market_data"
        self.params = {"ticker_symbol": ticker_symbol}
        return self

    def candles(self, ticker_symbol: str, timeframe) -> 'BacktestRestBuilder[T, list[Candle]]':
        self.method_name = "candles"
        self.params = {"ticker_symbol": ticker_symbol, "timeframe": timeframe}
        return self

    def account_balance(self) -> 'BacktestRestBuilder[T, list[AccountBalance]]':
        self.method_name = "account_balance"
        self.params = {}
        return self

    def account_fees(self) -> 'BacktestRestBuilder[T, Fees]':
        self.method_name = "account_fees"
        self.params = {}
        return self

    def instrument_fees(self, ticker_symbol: str) -> 'BacktestRestBuilder[T, Fees]':
        self.method_name = "instrument_fees"
        self.params = {"ticker_symbol": ticker_symbol}
        return self

    def create_order(
            self,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: Decimal,
            trade_action
    ) -> 'BacktestRestBuilder[T, None]':
        self.method_name = "create_order"
        self.params = {
            "uuid": uuid,
            "ticker_symbol": ticker_symbol,
            "quantity": quantity,
            "price": str(price),
            "trade_action": trade_action
        }
        return self

    def get_order(self, uuid: str) -> 'BacktestRestBuilder[T, Order]':
        self.method_name = "get_order"
        self.params = {"uuid": uuid}
        return self

    def cancel_order(self, uuid: str) -> 'BacktestRestBuilder[T, None]':
        self.method_name = "cancel_order"
        self.params = {"uuid": uuid}
        return self
