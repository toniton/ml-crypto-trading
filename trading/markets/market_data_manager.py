from __future__ import annotations

import logging

from entities.asset import Asset
from api.interfaces.market_data import MarketData
from trading.markets.market_data_client import MarketDataClient
from api.interfaces.exchange_provider import ExchangeProvider


class MarketDataManager:

    def __init__(self, assets: list[Asset]):
        self.assets = assets
        self.market_data: dict[int, MarketData] = {}
        self.market_data_clients = {}
        self.providers: dict[str, ExchangeProvider] = {}

    def register_provider(self, provider: ExchangeProvider):
        if provider.get_provider_name() in self.providers:
            raise ValueError(f"Provider ${provider.get_provider_name()} already registered.")

        self.providers[provider.get_provider_name()] = provider

    def init_websocket(self):
        if not self.providers:
            logging.warning([
                "No interfaces registered yet for Marketdata functionality."
            ])
            pass

        for asset in self.assets:
            (key, ticker_symbol, exchange) = asset.key, asset.ticker_symbol, asset.exchange
            provider = self.providers[exchange.value]
            self.market_data_clients[key] = MarketDataClient(
                key, ticker_symbol, provider, self.on_marketdata_update,
            )

        for client in self.market_data_clients.values():
            client.start()

    def on_marketdata_update(self, key: int, data: MarketData):
        logging.warning(["Market data for key:", key, ", updates received:", data])
        self.market_data[key] = data

    def get_latest_marketdata(self, asset: Asset) -> MarketData | None:
        key = asset.key
        if key in self.market_data:
            return self.market_data[key]

        return None
