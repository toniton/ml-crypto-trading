from __future__ import annotations

from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.core.registries.rest_client_registry import RestClientRegistry
from src.core.registries.websocket_registry import WebSocketRegistry


class MarketDataManager(ApplicationLoggingMixin, RestClientRegistry, WebSocketRegistry):
    MAX_CANDLES = 50

    def __init__(self, assets: list[Asset]):
        super().__init__()
        self.assets = assets
        self.market_data: dict[int, MarketData] = {}
        self.candles: dict[int, list[Candle]] = {asset.key: [] for asset in assets}

    def init_websocket(self):
        for asset in self.assets:
            (key, ticker_symbol, exchange,
             timeframe) = asset.key, asset.ticker_symbol, asset.exchange, asset.candles_timeframe
            self.get_candles(asset)
            websocket_client = self.get_websocket(exchange.value)
            websocket_client.subscribe_market_data(
                ticker_symbol, callback=self._ws_marketdata_callback(key)
            )
            websocket_client.subscribe_candles(
                ticker_symbol, timeframe, callback=self._ws_candles_callback(key)
            )

    def _ws_marketdata_callback(self, asset_key: int):
        def _on_marketdata_update(conn_key: str, data: MarketData):
            self.app_logger.debug(f"Market update: {asset_key} @ {data.close_price} (from {conn_key})")
            self.market_data[asset_key] = data

        return _on_marketdata_update

    def _ws_candles_callback(self, asset_key: int):
        def _on_candles_update(conn_key: str, new_candles: list[Candle]):
            self.app_logger.debug(f"Candles update: {asset_key} @ {new_candles} (from {conn_key})")
            self._update_candles(asset_key, new_candles)

        return _on_candles_update

    def get_latest_marketdata(self, key: int) -> MarketData | None:
        if key in self.market_data:
            return self.market_data[key]
        return None

    def get_market_data(self, ticker_symbol: str, provider_name: str) -> MarketData:
        provider = self.get_client(provider_name)
        return provider.get_market_data(ticker_symbol)

    def _update_candles(self, asset_key: int, new_candles: list[Candle]) -> None:
        self.candles[asset_key].extend(new_candles)
        self.candles[asset_key].sort(key=lambda candle: candle.start_time)

        if len(self.candles[asset_key]) > self.MAX_CANDLES:
            excess = len(self.candles[asset_key]) - self.MAX_CANDLES
            del self.candles[asset_key][:excess]

    def get_candles(self, asset: Asset) -> list[Candle]:
        if len(self.candles[asset.key]) == 0:
            provider = self.get_client(asset.exchange.value)
            new_candles = provider.get_candles(asset.ticker_symbol, asset.candles_timeframe)
            self._update_candles(asset.key, new_candles)

        return self.candles[asset.key].copy()
