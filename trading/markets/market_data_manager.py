from __future__ import annotations

import logging
from typing import Any

from entities.asset import Asset
from entities.market_data import MarketData
from trading.mappers.mapper_manager import MapperManager
from trading.markets.market_data_client import MarketDataClient
from trading.providers.exchange_provider import ExchangeProvider


class MarketDataManager:

    def __init__(self, assets: list[Asset]):
        self.assets = assets
        self.market_data: dict[int, MarketData] = {}
        self.market_data_clients = {}
        self.providers: dict[str, ExchangeProvider] = {}
        self.mapper_manager: MapperManager | None = None

    def register_provider(self, provider: ExchangeProvider):
        if provider.get_provider_name() in self.providers:
            raise ValueError(f"Provider ${provider.get_provider_name()} already registered.")

        self.providers[provider.get_provider_name()] = provider

    def set_mapper_manager(self, mapper_manager: MapperManager):
        self.mapper_manager = mapper_manager

    def init_websocket(self):
        if not self.providers:
            logging.warning([
                "No providers registered yet for Marketdata functionality."
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

    def on_marketdata_update(self, key: int, data: Any, provider_name: str):
        if self.mapper_manager is None:
            raise Exception(["Mapper required for market data manager."])

        logging.warning(["Market data for key:", key, ", updates received:", data])

        self.market_data[key] = self.mapper_manager.map(data, provider_name)

    def get_latest_marketdata(self, asset: Asset) -> MarketData | None:
        key = asset.key
        if key in self.market_data:
            return self.market_data[key]

        return None
