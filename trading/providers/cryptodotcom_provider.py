import hashlib
import hmac
import json
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

import websocket

from entities.exchange_provider import ExchangeProvidersEnum
from entities.market_data import MarketData
from entities.trade_action import TradeAction
from trading.helpers.trading_helper import TradingHelper
from trading.mappers.cryptodotcom_marketdata_mapper import CryptoDotComMarketDataMapper
from trading.providers.cryptodotcom_dto import CryptoDotComRequestDto, CryptoDotComResponseOrderCreatedDto
from trading.providers.exchange_provider import ExchangeProvider
from trading.providers.utils.helpers import params_to_str


class CryptoDotComProvider(ExchangeProvider):

    def __init__(self, base_url: str, websocket_url: str, api_key: str, secret_key: str):
        self.websocket_client = None
        self.base_url = base_url
        self.websocket_url = websocket_url
        self.api_key = api_key
        self.secret_key = secret_key

    def get_provider_name(self):
        return ExchangeProvidersEnum.CRYPTO_DOT_COM.name

    def init_http_connection(self, path: str, method: str = "GET", data: Any = None, headers: dict = None) -> Request:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            **(headers or {})
        }
        request = Request(url=self.base_url + path, method=method, headers=headers, data=data)
        return request

    def get_market_data(self, ticker_symbol: str) -> MarketData:
        instrument_name = TradingHelper.get_instrument_name(ticker_symbol)
        request = self.init_http_connection(
            f"public/get-ticker?instrument_name={instrument_name}-PERP&valuation_type=index_price&count=1"
        )

        with urlopen(request) as response:
            body = response.read()
            data = json.loads(body)

        return CryptoDotComMarketDataMapper.map(data)

    def _build_order_request(
            self,
            uuid: UUID,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction
    ) -> CryptoDotComRequestDto:
        instrument_name = TradingHelper.get_instrument_name(ticker_symbol, separator="_")
        nonce = int(time.time() * 1000)
        request_data = {
            "id": 1,
            "nonce": nonce,
            "method": "private/create-order",
            "api_key": self.api_key,
            "params": {
                "instrument_name": instrument_name,
                "side": trade_action.value.upper(),
                "type": "LIMIT",
                "price": price,
                "quantity": quantity,
                "client_oid": str(uuid),
                "exec_inst": "POST_ONLY",
                "time_in_force": "FILL_OR_KILL"
            }
        }

        payload_str = request_data['method'] \
            + str(request_data.get('id')) \
            + request_data['api_key'] \
            + params_to_str(request_data['params'], 0, 2) \
            + str(request_data['nonce'])

        request_data['sig'] = hmac.new(
            bytes(str(self.secret_key), 'utf-8'),
            msg=bytes(payload_str, 'utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()
        return CryptoDotComRequestDto(**request_data)

    def place_order(
            self,
            uuid: UUID,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction
    ) -> CryptoDotComResponseOrderCreatedDto:
        request_data = self._build_order_request(uuid, ticker_symbol, quantity, price, trade_action)
        serialized_json = request_data.model_dump_json()

        request = self.init_http_connection(
            "private/create-order",
            method="POST",
            data=serialized_json.encode("utf-8")
        )

        try:
            with urlopen(request) as response:
                body = response.read()
                data = json.loads(body)
            return CryptoDotComResponseOrderCreatedDto(**data["result"])
        except HTTPError as exc:
            raise Exception(exc, exc.read().decode())
        except URLError as exc:
            raise Exception(exc, exc.reason)

    def get_websocket_client(self, on_open: Callable, on_message: Callable, on_close: Callable):
        self.websocket_client = websocket.WebSocketApp(
            self.websocket_url, on_open=on_open,
            on_message=on_message, on_close=on_close
        )
        return self.websocket_client
