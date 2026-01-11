import hashlib
import hmac
import json
import time
from decimal import Decimal
from typing import Optional, Callable, TypeVar
from urllib.parse import urlencode
from urllib.request import Request
from pydantic import BaseModel

from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.trading.helpers.request_helper import RequestHelper
from src.core.interfaces.exchange_request_builder import Endpoint, ExchangeRequestBuilder
from src.clients.cryptodotcom.cryptodotcom_dto import (
    CryptoDotComMarketDataResponseDto,
    CryptoDotComCandleResponseDto,
    CryptoDotComResponseOrderGetDto, CryptoDotComUserBalanceResponseDto,
    CryptoDotComUserFeesResponseDto,
    CryptoDotComInstrumentFeesResponseDto,
    CryptoDotComResponseOrderCreatedDto
)
from src.clients.cryptodotcom.mappers.cryptodotcom_mapper import CryptoDotComMapper
from src.clients.cryptodotcom.utils.helpers import params_to_str

T = TypeVar('T', bound=BaseModel)


class CryptoDotComRequestBuilder(ExchangeRequestBuilder):

    def __init__(
            self,
            base_url: str,
            api_key: Optional[str] = None,
            secret_key: Optional[str] = None
    ):
        self._base_url = base_url
        self._api_key = api_key
        self._secret_key = secret_key
        self._endpoint: Optional[Endpoint] = None
        self._params: dict = {}
        self._dto_class = None
        self._request: Optional[Request] = None

    def _build_request(self) -> Request:
        if not self._endpoint:
            raise RuntimeError("Endpoint not set before execution")

        if self._endpoint.private:
            return self._build_private_request()
        return self._build_public_request()

    def _build_private_request(self) -> Request:
        request_data = {
            "id": int(time.time() * 1000),
            "nonce": int(time.time() * 1000),
            "method": self._endpoint.path,
            "api_key": self._api_key,
            "params": self._params
        }
        request_data['sig'] = self._generate_signature(request_data)

        return RequestHelper.create_request(
            self._base_url, self._endpoint.path, method="POST",
            data=json.dumps(request_data).encode("utf-8")
        )

    def _build_public_request(self) -> Request:
        query_string = urlencode(self._params)
        full_path = (
            f"{self._endpoint.path}?{query_string}"
            if query_string else self._endpoint.path
        )
        return RequestHelper.create_request(self._base_url, full_path)

    def _generate_signature(self, request_data: dict) -> str:
        payload_str = (
                request_data['method'] +
                str(request_data.get('id')) +
                request_data['api_key'] +
                params_to_str(request_data['params'], 0, 2) +
                str(request_data['nonce'])
        )
        return hmac.new(
            bytes(str(self._secret_key), 'utf-8'),
            msg=bytes(payload_str, 'utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

    def _set_endpoint(
            self,
            endpoint: Endpoint,
            params: dict
    ) -> 'CryptoDotComRequestBuilder':
        self._endpoint = endpoint
        self._params = params
        self._dto_class = endpoint.response_dto
        return self

    def _execute(self) -> dict:
        self._request = self._build_request()
        return RequestHelper.execute_request(self._request)

    def market_data(self, ticker_symbol: str) -> ExchangeRequestBuilder:
        endpoint = Endpoint(
            path="public/get-tickers",
            response_dto=CryptoDotComMarketDataResponseDto,
            private=False
        )
        return self._set_endpoint(
            endpoint,
            {
                "instrument_name": ticker_symbol,
                "valuation_type": "index_price",
                "count": "1"
            }
        )

    def candles(self, ticker_symbol: str, timeframe: Timeframe) -> ExchangeRequestBuilder:
        endpoint = Endpoint(
            path="public/get-candlestick",
            response_dto=CryptoDotComCandleResponseDto,
            private=False
        )
        interval = CryptoDotComMapper.from_timeframe(timeframe)
        return self._set_endpoint(
            endpoint,
            {
                "instrument_name": ticker_symbol,
                "timeframe": interval
            }
        )

    def account_balance(self) -> ExchangeRequestBuilder:
        endpoint = Endpoint(
            path="private/user-balance",
            response_dto=CryptoDotComUserBalanceResponseDto,
            private=True
        )
        return self._set_endpoint(
            endpoint,
            {}
        )

    def account_fees(self) -> ExchangeRequestBuilder:
        endpoint = Endpoint(
            path="private/get-fee-rate",
            response_dto=CryptoDotComUserFeesResponseDto,
            private=True
        )
        return self._set_endpoint(
            endpoint,
            {}
        )

    def instrument_fees(self, ticker_symbol: str) -> ExchangeRequestBuilder:
        endpoint = Endpoint(
            path="private/get-instrument-fee-rate",
            response_dto=CryptoDotComInstrumentFeesResponseDto,
            private=True
        )
        return self._set_endpoint(
            endpoint,
            {
                "instrument_name": ticker_symbol
            }
        )

    def create_order(
            self,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: Decimal,
            trade_action: TradeAction
    ) -> ExchangeRequestBuilder:
        endpoint = Endpoint(
            path="private/create-order",
            response_dto=CryptoDotComResponseOrderCreatedDto,
            private=True
        )
        return self._set_endpoint(
            endpoint,
            {
                "instrument_name": ticker_symbol,
                "side": trade_action.value.upper(),
                "type": "LIMIT",
                "price": str(price),
                "quantity": quantity,
                "client_oid": uuid,
                "exec_inst": ["POST_ONLY"],
                "time_in_force": "GOOD_TILL_CANCEL"
            }
        )

    def get_order(self, uuid: str) -> ExchangeRequestBuilder:
        endpoint = Endpoint(
            path="private/get-order-detail",
            response_dto=CryptoDotComResponseOrderGetDto,
            private=True
        )
        return self._set_endpoint(
            endpoint,
            {"client_oid": uuid}
        )

    def cancel_order(self, uuid: str) -> ExchangeRequestBuilder:
        endpoint = Endpoint(
            path="private/cancel-order",
            response_dto=CryptoDotComResponseOrderCreatedDto,
            private=True
        )
        return self._set_endpoint(
            endpoint,
            {"client_oid": uuid}
        )

    def execute(self, mapper: Optional[Callable] = None):
        response_data = self._execute()
        response_dto = self._dto_class(**response_data)
        return mapper(response_dto) if mapper else response_dto
