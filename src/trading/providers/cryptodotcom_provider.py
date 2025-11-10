from __future__ import annotations

import json
import logging
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import UUID

import websocket
from cachetools import TTLCache, cached

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.configuration.providers.cryptodotcom_config import CryptodotcomConfig
from src.trading.helpers.trading_helper import TradingHelper
from src.trading.providers.factories.cryptodotcom_request_factory import CryptoDotComRequestFactory
from src.trading.providers.mappers.cryptodotcom_mapper import CryptoDotComMapper
from src.trading.providers.cryptodotcom_dto import CryptoDotComResponseOrderCreatedDto, \
    CryptoDotComCandleResponseDto, CryptoDotComUserBalanceResponseDto
from api.interfaces.exchange_provider import ExchangeProvider, ExchangeProvidersEnum


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
        ticker_symbol = TradingHelper.format_ticker_symbol(ticker_symbol, suffix="-PERP")
        channels = [f"ticker.{ticker_symbol}"]
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
        request = CryptoDotComRequestFactory.build_market_data_request(self.base_url, ticker_symbol)

        try:
            with urlopen(request) as response:
                body = response.read()
                data = json.loads(body)
            return CryptoDotComMapper.to_marketdata(data)
        except HTTPError as exc:
            logging.warning(["Fetch marketdata api failure -> ", exc])
            raise RuntimeError(exc, exc.read().decode()) from exc
        except URLError as exc:
            logging.warning(["Fetch marketdata api failure -> ", exc])
            raise RuntimeError(exc, exc.reason) from exc

    @cached(cache=TTLCache(maxsize=2024, ttl=600))
    def get_account_balance(self, ticker_symbol: str) -> AccountBalance:
        base_ticker_symbol, quote_ticker_symbol = ticker_symbol.split("_")
        request = CryptoDotComRequestFactory.build_account_balance_request(
            self.base_url, self.api_key, self.secret_key
        )

        try:
            with urlopen(request) as response:
                body = response.read()
                data = json.loads(body)
            account_balance = CryptoDotComUserBalanceResponseDto(**data)
            return CryptoDotComMapper.to_account_balance(base_ticker_symbol, quote_ticker_symbol, account_balance)
        except HTTPError as exc:
            raise RuntimeError(exc, exc.read().decode()) from exc
        except URLError as exc:
            raise RuntimeError(exc, exc.reason) from exc

    def place_order(
            self,
            uuid: UUID,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction
    ) -> CryptoDotComResponseOrderCreatedDto:
        request = CryptoDotComRequestFactory.build_order_request(
            self.base_url, self.api_key, self.secret_key, uuid,
            ticker_symbol, quantity, price, trade_action
        )

        try:
            with urlopen(request) as response:
                body = response.read()
                data = json.loads(body)
            return CryptoDotComResponseOrderCreatedDto(**data["result"])
        except HTTPError as exc:
            raise RuntimeError(exc, exc.read().decode()) from exc
        except URLError as exc:
            raise RuntimeError(exc, exc.reason) from exc

    def get_websocket_client(self, on_open: Callable, on_message: Callable[[MarketData], None], on_close: Callable):
        def on_message_mapper(_on_message: Callable[[MarketData], None]):
            def map_data(ws, data):
                json_data = json.loads(data)
                if 'method' in json_data and json_data['method'] == 'public/heartbeat':
                    ws.send(json.dumps({
                        "id": json_data['id'],
                        "method": "public/respond-heartbeat",
                    }))
                    return
                _on_message(CryptoDotComMapper.to_marketdata(json_data))

            return map_data

        self.websocket_client = websocket.WebSocketApp(
            self.websocket_url, on_open=on_open,
            on_message=on_message_mapper(on_message), on_close=on_close
        )
        return self.websocket_client

    def get_candle(self, ticker_symbol: str, timeframe: Timeframe) -> list[Candle]:
        request = CryptoDotComRequestFactory.build_get_candle_request(self.base_url, ticker_symbol, timeframe)

        try:
            with urlopen(request) as response:
                body = response.read()
                data = json.loads(body)
            candle_response = CryptoDotComCandleResponseDto(**data)
            return CryptoDotComMapper.to_candles(candle_response)
        except HTTPError as exc:
            raise RuntimeError(exc, exc.read().decode()) from exc
        except URLError as exc:
            raise RuntimeError(exc, exc.reason) from exc
