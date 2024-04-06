from __future__ import annotations

import json
from typing import Callable

from api.interfaces.exchange_provider import ExchangeProvider
from api.interfaces.market_data import MarketData


class MarketDataClient:
    def __init__(
            self, key: int, ticker_symbol: str,
            provider: ExchangeProvider,
            on_update: Callable[[int, MarketData], None]
    ):
        self.key: int = key
        self.ticker_symbol: str = ticker_symbol
        self.provider: ExchangeProvider = provider
        self.on_update = on_update

    def on_open(self, ws):
        print('Connected')
        subscription_data = self.provider.get_market_subscription_data(self.ticker_symbol)
        if subscription_data is not None:
            ws.send(json.dumps(subscription_data))

    @classmethod
    def on_close(cls, ws):
        print('Disconnected')

    def on_message(self, data: MarketData):
        self.on_update(self.key, data)

    def start(self):
        websocket_client = self.provider.get_websocket_client(
            on_open=self.on_open, on_message=self.on_message,
            on_close=self.on_close
        )
        websocket_client.run_forever()
