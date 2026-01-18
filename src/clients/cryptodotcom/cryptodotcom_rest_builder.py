from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Generic, Optional, TypeVar
from urllib.parse import urlencode
from urllib.request import Request
from pydantic import BaseModel

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.clients.cryptodotcom.mappers.cryptodotcom_mappers import CryptoDotComAccountBalanceMapper, \
    CryptoDotComCandleMapper, \
    CryptoDotComFeesMapper, CryptoDotComInstrumentFeesMapper, CryptoDotComMarketDataMapper, CryptoDotComOrderMapper
from src.core.interfaces.mapper import Mapper
from src.clients.cryptodotcom.utils.timeframe_map import CryptoDotComTimeframe
from src.trading.helpers.request_helper import RequestHelper
from src.core.interfaces.exchange_rest_builder import Endpoint, ExchangeRestBuilder
from src.clients.cryptodotcom.utils.helpers import params_to_str

T = TypeVar('T', bound=BaseModel)


class CryptoDotComRestBuilder(Generic[T], ExchangeRestBuilder[dict, T]):

    def __init__(self):
        super().__init__()
        self._endpoint: Optional[Endpoint] = None
        self._params: dict = {}
        self._signature: dict = {}

    def mapper(self) -> Mapper[dict, T] | None:
        return self._mapper

    def sign(self, api_key: str, secret_key: str) -> 'CryptoDotComRestBuilder':
        if not self._endpoint.private:
            return self

        request_id = int(time.time() * 1000)
        nonce = int(time.time() * 1000)

        payload_str = self._build_signature_payload(api_key, request_id, nonce)
        signature = hmac.new(
            bytes(str(secret_key), 'utf-8'),
            msg=bytes(payload_str, 'utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

        self._signature = {
            "api_key": api_key,
            "sig": signature,
            "id": request_id,
            "nonce": nonce
        }
        return self

    def build_request(self, base_url: str) -> Request:
        if not self._endpoint:
            raise RuntimeError("Endpoint not set before execution")

        if self._endpoint.private:
            return self._build_private_request(base_url)
        return self._build_public_request(base_url)

    def _build_private_request(self, base_url: str) -> Request:
        request_data = {
            "id": self._signature["id"],
            "nonce": self._signature["nonce"],
            "method": self._endpoint.path,
            "params": self._params,
            "api_key": self._signature["api_key"],
            "sig": self._signature["sig"]
        }

        return RequestHelper.create_request(
            base_url, self._endpoint.path, method="POST",
            data=json.dumps(request_data).encode("utf-8")
        )

    def _build_public_request(self, base_url: str) -> Request:
        query_string = urlencode(self._params)
        full_path = (
            f"{self._endpoint.path}?{query_string}"
            if query_string else self._endpoint.path
        )
        return RequestHelper.create_request(base_url, full_path)

    def _build_signature_payload(self, api_key: str, request_id: int, nonce: int) -> str:
        return (
                self._endpoint.path +
                str(request_id) +
                api_key +
                params_to_str(self._params, 0, 2) +
                str(nonce)
        )

    def market_data(self, ticker_symbol: str) -> CryptoDotComRestBuilder[Optional[MarketData]]:
        endpoint = Endpoint(
            path="public/get-tickers",
            private=False,
            mapper=CryptoDotComMarketDataMapper()
        )
        return self._set_endpoint(
            endpoint,
            {
                "instrument_name": ticker_symbol
            }
        )

    def candles(self, ticker_symbol: str, timeframe: Timeframe) -> CryptoDotComRestBuilder[list[Candle]]:
        endpoint = Endpoint(
            path=f"public/get-candlestick?instrument_name={ticker_symbol}&timeframe={CryptoDotComTimeframe.MAP.get(timeframe)}",
            private=False,
            mapper=CryptoDotComCandleMapper()
        )
        return self._set_endpoint(endpoint)

    def account_balance(self) -> CryptoDotComRestBuilder[AccountBalance]:
        endpoint = Endpoint(
            path="private/user-balance",
            private=True,
            mapper=CryptoDotComAccountBalanceMapper()
        )
        return self._set_endpoint(endpoint)

    def account_fees(self) -> CryptoDotComRestBuilder[Fees]:
        endpoint = Endpoint(
            path="private/get-fee-rate",
            private=True,
            mapper=CryptoDotComFeesMapper()
        )
        return self._set_endpoint(endpoint)

    def instrument_fees(self, ticker_symbol: str) -> CryptoDotComRestBuilder[Fees]:
        endpoint = Endpoint(
            path="private/get-instrument-fee-rate",
            private=True,
            mapper=CryptoDotComInstrumentFeesMapper()
        )
        return self._set_endpoint(endpoint, {"instrument_name": ticker_symbol})

    def create_order(
            self,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction
    ) -> CryptoDotComRestBuilder[None]:
        endpoint = Endpoint(
            path="private/create-order",
            private=True,
        )
        self._set_endpoint(endpoint, {
            "instrument_name": ticker_symbol,
            "side": trade_action.value,
            "type": "LIMIT",
            "price": price,
            "quantity": quantity,
            "client_oid": uuid,
            "time_in_force": "GOOD_TILL_CANCEL"
        })
        return self

    def get_order(self, uuid: str) -> CryptoDotComRestBuilder[Order]:
        endpoint = Endpoint(
            path="private/get-order-detail",
            private=True,
            mapper=CryptoDotComOrderMapper()
        )
        return self._set_endpoint(endpoint, {"client_oid": uuid})

    def cancel_order(self, uuid: str) -> CryptoDotComRestBuilder[None]:
        endpoint = Endpoint(
            path="private/cancel-order",
            private=True
        )
        return self._set_endpoint(endpoint, {"client_oid": uuid})

    def _set_endpoint(self, endpoint: Endpoint, params: dict = None) -> CryptoDotComRestBuilder:
        self._endpoint = endpoint
        self._mapper = endpoint.mapper
        self._params = params or {}
        return self
