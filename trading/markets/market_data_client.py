from __future__ import annotations

import json
from typing import Callable

from trading.providers.exchange_provider import ExchangeProvider


class MarketDataClient:
    def __init__(
            self, key: int, ticker_symbol: str,
            provider: ExchangeProvider,
            on_update: Callable[[int, dict, str], None],
            default_action_data: dict | None = None
    ):
        self.key: int = key
        self.ticker_symbol: str = ticker_symbol
        self.provider: ExchangeProvider = provider
        self.default_action_data = default_action_data
        self.on_update = on_update

    def on_open(self, ws):
        print('Connected')
        if self.default_action_data is not None:
            ws.send(json.dumps(self.default_action_data))

    @classmethod
    def on_close(cls, ws):
        print('Disconnected')

    def on_message(self, ws, message):
        json_msg = json.loads(message)
        self.on_update(self.key, json_msg, self.provider.get_provider_name())

    def start(self):
        websocket_client = self.provider.get_websocket_client(
            on_open=self.on_open, on_message=self.on_message,
            on_close=self.on_close
        )
        websocket_client.run_forever()
