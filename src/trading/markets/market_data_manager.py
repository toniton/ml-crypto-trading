from __future__ import annotations

import logging

from api.interfaces.asset import Asset
from api.interfaces.market_data import MarketData
from src.core.registries.provider_registry import ProviderRegistry
from src.trading.markets.market_data_client import MarketDataClient


class MarketDataManager(ProviderRegistry):

    def __init__(self, assets: list[Asset]):
        super().__init__()
        self.assets = assets
        self.market_data: dict[int, MarketData] = {}
        self.market_data_clients = {}

    def init_websocket(self):
        if not self.providers:
            logging.warning([
                "No interfaces registered yet for Marketdata functionality."
            ])
            pass

        for asset in self.assets:
            (key, ticker_symbol, exchange) = asset.key, asset.ticker_symbol, asset.exchange
            provider = self.get_provider(exchange.value)
            self.market_data_clients[key] = MarketDataClient(
                key, ticker_symbol, provider, self.on_marketdata_update,
            )

        for client in self.market_data_clients.values():
            client.start()

    def on_marketdata_update(self, key: int, data: MarketData):
        logging.warning(["Market data for key:", key, ", updates received:", data])
        self.market_data[key] = data

    def get_latest_marketdata(self, key: int) -> MarketData | None:
        if key in self.market_data:
            return self.market_data[key]

        return None
