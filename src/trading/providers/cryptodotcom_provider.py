from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import UUID

import websocket

from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.configuration.providers.cryptodotcom_config import CryptodotcomConfig
from src.trading.helpers.request_helper import RequestHelper
from src.trading.helpers.trading_helper import TradingHelper
from src.trading.providers.mappers.cryptodotcom_marketdata_mapper import CryptoDotComMapper
from src.trading.providers.cryptodotcom_dto import CryptoDotComRequestDto, CryptoDotComResponseOrderCreatedDto, \
    CryptoDotComCandleResponseDto
from api.interfaces.exchange_provider import ExchangeProvider, ExchangeProvidersEnum
from src.trading.providers.utils.helpers import params_to_str


class CryptoDotComProvider(ExchangeProvider):

    def __init__(self):
        config = CryptodotcomConfig.get_instance()
        self.websocket_client = None
        self.base_url = config.base_url
        self.websocket_url = config.websocket_url
        self.api_key = config.api_key
        self.secret_key = config.secret_key

    def get_provider_name(self):
        return ExchangeProvidersEnum.CRYPTO_DOT_COM.name

    def get_market_subscription_data(self, ticker_symbol: str) -> dict | None:
        channels = [f"ticker.{TradingHelper.get_instrument_name(ticker_symbol)}-PERP"]
        data = {
            "id": 1,
            "method": "subscribe",
            "params": {
                "channels": channels
            },
            "nonce": int(time.time())
        }
        return data

    def get_market_data(self, ticker_symbol: str) -> MarketData:
        instrument_name = TradingHelper.get_instrument_name(ticker_symbol)
        request = RequestHelper.init_http_connection(
            self.base_url,
            f"public/get-ticker?instrument_name={instrument_name}-PERP&valuation_type=index_price&count=1"
        )

        with urlopen(request) as response:
            body = response.read()
            data = json.loads(body)

        return CryptoDotComMapper.to_marketdata(data)

    def _build_order_request(
            self,
            uuid: UUID,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction
    ) -> CryptoDotComRequestDto:
        instrument_name = TradingHelper.get_instrument_name(ticker_symbol, separator="", perp=True)
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
                "exec_inst": ["POST_ONLY"],
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

        request = RequestHelper.init_http_connection(
            self.base_url,
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

    def get_websocket_client(self, on_open: Callable, on_message: Callable[[MarketData], None], on_close: Callable):
        def on_message_mapper(_on_message: Callable[[MarketData], None]):
            def map_data(ws, data):
                json_data = json.loads(data)
                _on_message(CryptoDotComMapper.to_marketdata(json_data))

            return map_data

        self.websocket_client = websocket.WebSocketApp(
            self.websocket_url, on_open=on_open,
            on_message=on_message_mapper(on_message), on_close=on_close
        )
        return self.websocket_client

    def get_candle(self, ticker_symbol: str, timeframe: Timeframe) -> list[Candle]:
        instrument_name = TradingHelper.get_instrument_name(ticker_symbol)
        interval = CryptoDotComMapper.from_timeframe(timeframe)
        request = RequestHelper.init_http_connection(
            self.base_url,
            f"public/get-candlestick?instrument_name={instrument_name}-PERP&timeframe={interval}"
        )

        with urlopen(request) as response:
            body = response.read()
            data = json.loads(body)

        candle_response = CryptoDotComCandleResponseDto(**data)

        return CryptoDotComMapper.to_candles(candle_response)
