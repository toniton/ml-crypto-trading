from __future__ import annotations

from urllib.error import HTTPError
from cachetools import TTLCache, cached
from circuitbreaker import circuit

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.configuration.exchanges_config import ExchangesConfig
from src.clients.cryptodotcom.cryptodotcom_request_builder import CryptoDotComRequestBuilder
from src.clients.cryptodotcom.mappers.cryptodotcom_mapper import CryptoDotComMapper
from src.core.interfaces.exchange_rest_client import ExchangeRestClient, ExchangeProvidersEnum


class CryptoDotComRestClient(ExchangeRestClient):

    def __init__(self):
        config = ExchangesConfig()
        self._base_url = config.crypto_dot_com.rest_endpoint
        self._api_key = config.crypto_dot_com.api_key
        self._secret_key = config.crypto_dot_com.secret_key

    def get_provider_name(self):
        return ExchangeProvidersEnum.CRYPTO_DOT_COM.name

    def _builder(self) -> CryptoDotComRequestBuilder:
        return CryptoDotComRequestBuilder(
            self._base_url, self._api_key, self._secret_key
        )

    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_market_data(self, ticker_symbol: str) -> MarketData:
        return self._builder().market_data(ticker_symbol).execute(
            mapper=CryptoDotComMapper.to_marketdata
        )

    @cached(cache=TTLCache(maxsize=2024, ttl=600))
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_account_balance(self) -> list[AccountBalance]:
        return self._builder().account_balance().execute(
            mapper=CryptoDotComMapper.to_account_balance
        )

    @cached(cache=TTLCache(maxsize=2024, ttl=6000))
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_account_fees(self) -> Fees:
        return self._builder().account_fees().execute(
            mapper=CryptoDotComMapper.to_fees
        )

    @cached(cache=TTLCache(maxsize=2024, ttl=6000))
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_instrument_fees(self, ticker_symbol: str) -> Fees:
        return self._builder().instrument_fees(ticker_symbol).execute(
            mapper=CryptoDotComMapper.to_instrument_fees
        )

    def place_order(
            self,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction
    ) -> None:
        self._builder().create_order(
            uuid, ticker_symbol, quantity, price, trade_action
        ).execute()

    def get_order(self, uuid: str) -> Order:
        return self._builder().get_order(uuid).execute(
            mapper=CryptoDotComMapper.to_order
        )

    def cancel_order(self, uuid: str) -> None:
        self._builder().cancel_order(uuid).execute()

    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_candles(self, ticker_symbol: str, timeframe: Timeframe) -> list[Candle]:
        return self._builder().candles(ticker_symbol, timeframe).execute(
            mapper=CryptoDotComMapper.to_candles
        )
