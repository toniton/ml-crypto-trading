from __future__ import annotations

from typing import Optional

from api.interfaces.timeframe import Timeframe
from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.subscription_data import SubscriptionData, SubscriptionVisibility
from src.exchange.clients.ccxt.ccxt_mapper import CCXTMapperFactory, CCXTTimeframe


class CCXTExchangeWebSocketBuilder(ExchangeWebSocketBuilder):
    def __init__(self, provider_name: str):
        self._provider_name: str = provider_name
        self._ticker_symbol: Optional[str] = None
        self._timeframe: Optional[str] = None
        self._type: Optional[str] = None
        self._visibility: SubscriptionVisibility = SubscriptionVisibility.PUBLIC

    def market_data(self, ticker_symbol: str) -> 'CCXTExchangeWebSocketBuilder':
        self._ticker_symbol = ticker_symbol
        self._type = 'ticker'
        self._visibility = SubscriptionVisibility.PUBLIC
        return self

    def candles(self, ticker_symbol: str, timeframe: Timeframe) -> 'CCXTExchangeWebSocketBuilder':
        self._ticker_symbol = ticker_symbol
        self._timeframe = CCXTTimeframe.MAP.get(timeframe)
        self._type = 'ohlcv'
        self._visibility = SubscriptionVisibility.PUBLIC
        return self

    def account_balance(self) -> 'CCXTExchangeWebSocketBuilder':
        self._type = 'balance'
        self._visibility = SubscriptionVisibility.PRIVATE
        return self

    def order_update(self, instrument_name: str) -> 'CCXTExchangeWebSocketBuilder':
        self._ticker_symbol = instrument_name
        self._type = 'orders'
        self._visibility = SubscriptionVisibility.PRIVATE
        return self

    @property
    def key(self) -> str | None:
        if not self._type:
            return None
        key = f"{self._type}_{self._ticker_symbol}"
        if self._timeframe:
            key += f"_{self._timeframe}"
        return key

    def get_subscription_data(self) -> SubscriptionData:
        payload = {
            'type': self._type,
            'symbol': self._ticker_symbol,
            'timeframe': self._timeframe or None
        }

        mapper = CCXTMapperFactory.get_mapper(self._type, self._provider_name)

        def matches(data: dict) -> bool:
            if not isinstance(data, dict):
                return False

            msg_type = data.get('type')
            msg_symbol = data.get('symbol')

            if msg_type != self._type:
                return False

            if self._ticker_symbol and msg_symbol != self._ticker_symbol:
                return False

            return True

        return SubscriptionData(
            payload=payload,
            visibility=self._visibility,
            parser=lambda d: mapper.map(d['data']) if mapper else d['data'],
            filter=matches
        )

    def get_unsubscribe_payload(self, subscribe_payload: dict) -> dict:
        return {**subscribe_payload, 'unsubscribe': True}
