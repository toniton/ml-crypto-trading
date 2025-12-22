from __future__ import annotations

import logging

from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from src.core.registries.rest_client_registry import RestClientRegistry
from src.core.registries.websocket_registry import WebSocketRegistry


class MarketDataManager(RestClientRegistry, WebSocketRegistry):

    def __init__(self, assets: list[Asset]):
        super().__init__()
        self.assets = assets
        self.market_data: dict[int, MarketData] = {}

    def init_websocket(self):
        for asset in self.assets:
            (key, ticker_symbol, exchange) = asset.key, asset.ticker_symbol, asset.exchange
            websocket_client = self.get_websocket(exchange.value)
            websocket_client.subscribe_market_data(
                ticker_symbol, callback=lambda conn_key, data, asset_key=key: self.on_marketdata_update(asset_key, data)
            )

    def on_marketdata_update(self, key: int, data: MarketData):
        logging.warning(["Market data for key:", key, ", updates received:", data])
        self.market_data[key] = data

    def get_latest_marketdata(self, key: int) -> MarketData | None:
        if key in self.market_data:
            return self.market_data[key]
        return None

    def get_market_data(self, ticker_symbol: str, provider_name: str) -> MarketData:
        provider = self.get_client(provider_name)
        return provider.get_market_data(ticker_symbol)

    def get_candles(self, provider_name: str, ticker_symbol: str, timeframe: Timeframe) -> list[Candle]:
        provider = self.get_client(provider_name)
        return provider.get_candle(ticker_symbol, timeframe)
