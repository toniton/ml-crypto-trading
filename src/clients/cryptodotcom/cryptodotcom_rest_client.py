from __future__ import annotations

from urllib.error import HTTPError


from cachetools import TTLCache, cached
from circuitbreaker import circuit

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.configuration.exchanges_config import ExchangesConfig
from src.trading.helpers.request_helper import RequestHelper
from src.clients.cryptodotcom.factories.cryptodotcom_request_factory import CryptoDotComRequestFactory
from src.clients.cryptodotcom.mappers.cryptodotcom_mapper import CryptoDotComMapper
from src.clients.cryptodotcom.cryptodotcom_dto import CryptoDotComInstrumentFeesResponseDto, \
    CryptoDotComMarketDataResponseDto, CryptoDotComResponseOrderCreatedDto, \
    CryptoDotComCandleResponseDto, CryptoDotComUserBalanceResponseDto, CryptoDotComUserFeesResponseDto
from src.core.interfaces.exchange_rest_client import ExchangeRestClient, ExchangeProvidersEnum


class CryptoDotComRestClient(ExchangeRestClient):
    def __init__(self):
        config = ExchangesConfig()
        self._base_url = config.crypto_dot_com.rest_endpoint
        self._api_key = config.crypto_dot_com.api_key
        self._secret_key = config.crypto_dot_com.secret_key

    def get_provider_name(self):
        return ExchangeProvidersEnum.CRYPTO_DOT_COM.name

    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_market_data(self, ticker_symbol: str) -> MarketData:
        request = CryptoDotComRequestFactory.build_market_data_request(self._base_url, ticker_symbol)
        response_data = RequestHelper.execute_request(request)
        market_data = CryptoDotComMarketDataResponseDto(**response_data)
        return CryptoDotComMapper.to_marketdata(market_data)

    @cached(cache=TTLCache(maxsize=2024, ttl=600))
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_account_balance(self) -> list[AccountBalance]:
        request = CryptoDotComRequestFactory.build_account_balance_request(
            self._base_url, self._api_key, self._secret_key
        )
        response_data = RequestHelper.execute_request(request)
        account_balance = CryptoDotComUserBalanceResponseDto(**response_data)
        return CryptoDotComMapper.to_account_balance(account_balance)

    @cached(cache=TTLCache(maxsize=2024, ttl=6000))
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_account_fees(self) -> Fees:
        request = CryptoDotComRequestFactory.build_account_fees_request(
            self._base_url, self._api_key, self._secret_key
        )
        response_data = RequestHelper.execute_request(request)
        account_fees = CryptoDotComUserFeesResponseDto(**response_data)
        return CryptoDotComMapper.to_fees(account_fees)

    @cached(cache=TTLCache(maxsize=2024, ttl=6000))
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_instrument_fees(self, ticker_symbol: str) -> Fees:
        request = CryptoDotComRequestFactory.build_instrument_fees_request(
            self._base_url, self._api_key, self._secret_key, ticker_symbol
        )
        response_data = RequestHelper.execute_request(request)
        account_balance = CryptoDotComInstrumentFeesResponseDto(**response_data)
        return CryptoDotComMapper.to_instrument_fees(account_balance)

    def place_order(
            self,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction
    ) -> CryptoDotComResponseOrderCreatedDto:
        request = CryptoDotComRequestFactory.build_order_request(
            self._base_url, self._api_key, self._secret_key, uuid,
            ticker_symbol, quantity, price, trade_action
        )
        response_data = RequestHelper.execute_request(request)
        return CryptoDotComResponseOrderCreatedDto(**response_data)

    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_candle(self, ticker_symbol: str, timeframe: Timeframe) -> list[Candle]:
        request = CryptoDotComRequestFactory.build_get_candle_request(self._base_url, ticker_symbol, timeframe)
        response_data = RequestHelper.execute_request(request)
        candle_response = CryptoDotComCandleResponseDto(**response_data)
        return CryptoDotComMapper.to_candles(candle_response)
