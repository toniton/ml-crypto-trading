from __future__ import annotations

import logging

from api.interfaces.asset import Asset
from api.interfaces.market_data import MarketData
from src.core.registries.provider_registry import ProviderRegistry
from src.core.registries.websocket_registry import WebSocketRegistry
from src.trading.helpers.trading_helper import TradingHelper


class MarketDataManager(ProviderRegistry, WebSocketRegistry):

    def __init__(self, assets: list[Asset]):
        super().__init__()
        self.assets = assets
        self.market_data: dict[int, MarketData] = {}

    def init_websocket(self):
        for asset in self.assets:
            (key, ticker_symbol, exchange) = asset.key, asset.ticker_symbol, asset.exchange
            websocket_client = self.get_websocket(exchange.value)
            ticker_symbol = TradingHelper.format_ticker_symbol(ticker_symbol)
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
