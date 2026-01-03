from __future__ import annotations

from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.core.registries.rest_client_registry import RestClientRegistry
from src.core.registries.websocket_registry import WebSocketRegistry


class MarketDataManager(ApplicationLoggingMixin, RestClientRegistry, WebSocketRegistry):

    def __init__(self, assets: list[Asset]):
        super().__init__()
        self.assets = assets
        self.market_data: dict[int, MarketData] = {}

    def init_websocket(self):
        for asset in self.assets:
            (key, ticker_symbol, exchange) = asset.key, asset.ticker_symbol, asset.exchange
            websocket_client = self.get_websocket(exchange.value)
            websocket_client.subscribe_market_data(
                ticker_symbol, callback=self._ws_callback(key)
            )

    def _ws_callback(self, asset_key: int):
        def _on_marketdata_update(conn_key: str, data: MarketData):
            self.app_logger.debug(f"Market update: {asset_key} @ {data.close_price} (from {conn_key})")
            self.market_data[asset_key] = data

        return _on_marketdata_update

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
