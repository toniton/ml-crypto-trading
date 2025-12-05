from __future__ import annotations

import json
import time
from typing import Callable
from urllib.error import HTTPError
from uuid import UUID

import websocket
from cachetools import TTLCache, cached
from circuitbreaker import circuit

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.configuration.providers.cryptodotcom_config import CryptodotcomConfig
from src.trading.helpers.request_helper import RequestHelper
from src.trading.providers.factories.cryptodotcom_request_factory import CryptoDotComRequestFactory
from src.trading.providers.mappers.cryptodotcom_mapper import CryptoDotComMapper
from src.trading.providers.cryptodotcom_dto import CryptoDotComInstrumentFeesResponseDto, \
    CryptoDotComMarketDataResponseDto, CryptoDotComResponseOrderCreatedDto, \
    CryptoDotComCandleResponseDto, CryptoDotComUserBalanceResponseDto, CryptoDotComUserFeesResponseDto
from src.core.interfaces.exchange_provider import ExchangeProvider, ExchangeProvidersEnum


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

    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_market_data(self, ticker_symbol: str) -> MarketData:
        request = CryptoDotComRequestFactory.build_market_data_request(self.base_url, ticker_symbol)
        response_data = RequestHelper.execute_request(request)
        market_data = CryptoDotComMarketDataResponseDto(**response_data)
        return CryptoDotComMapper.to_marketdata(market_data)

    @cached(cache=TTLCache(maxsize=2024, ttl=600))
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_account_balance(self) -> list[AccountBalance]:
        request = CryptoDotComRequestFactory.build_account_balance_request(
            self.base_url, self.api_key, self.secret_key
        )
        response_data = RequestHelper.execute_request(request)
        account_balance = CryptoDotComUserBalanceResponseDto(**response_data)
        return CryptoDotComMapper.to_account_balance(account_balance)

    @cached(cache=TTLCache(maxsize=2024, ttl=6000))
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_account_fees(self) -> Fees:
        request = CryptoDotComRequestFactory.build_account_fees_request(
            self.base_url, self.api_key, self.secret_key
        )
        response_data = RequestHelper.execute_request(request)
        account_fees = CryptoDotComUserFeesResponseDto(**response_data)
        return CryptoDotComMapper.to_fees(account_fees)

    @cached(cache=TTLCache(maxsize=2024, ttl=6000))
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_instrument_fees(self, ticker_symbol: str) -> Fees:
        request = CryptoDotComRequestFactory.build_instrument_fees_request(
            self.base_url, self.api_key, self.secret_key, ticker_symbol
        )
        response_data = RequestHelper.execute_request(request)
        account_balance = CryptoDotComInstrumentFeesResponseDto(**response_data)
        return CryptoDotComMapper.to_instrument_fees(account_balance)

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
        response_data = RequestHelper.execute_request(request)
        return CryptoDotComResponseOrderCreatedDto(**response_data)

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

                response_data = CryptoDotComMarketDataResponseDto(**json_data)
                _on_message(CryptoDotComMapper.to_marketdata(response_data))

            return map_data

        self.websocket_client = websocket.WebSocketApp(
            self.websocket_url, on_open=on_open,
            on_message=on_message_mapper(on_message), on_close=on_close
        )
        return self.websocket_client

    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_candle(self, ticker_symbol: str, timeframe: Timeframe) -> list[Candle]:
        request = CryptoDotComRequestFactory.build_get_candle_request(self.base_url, ticker_symbol, timeframe)
        response_data = RequestHelper.execute_request(request)
        candle_response = CryptoDotComCandleResponseDto(**response_data)
        return CryptoDotComMapper.to_candles(candle_response)
