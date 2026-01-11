from __future__ import annotations


from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.core.registries.rest_client_registry import RestClientRegistry
from src.core.registries.websocket_registry import WebSocketRegistry
from src.clients.websocket_manager import WebSocketManager


class MarketDataManager(ApplicationLoggingMixin, RestClientRegistry, WebSocketRegistry):
    MAX_CANDLES = 50

    def __init__(self, websocket_manager: WebSocketManager):
        super().__init__()
        self._websocket_manager = websocket_manager
        self._assets: list[Asset] = []
        self._market_data: dict[int, MarketData | None] = {}
        self._candles: dict[int, list[Candle]] = {}
        self._last_market_data_updated: float = 0.0

    def initialize(self, assets: list[Asset]):
        self._assets = assets
        for asset in assets:
            self._market_data[asset.key] = None
            self._candles[asset.key] = []
            (key, ticker_symbol, exchange,
             timeframe) = asset.key, asset.ticker_symbol, asset.exchange, asset.candles_timeframe
            self.get_candles(asset)
            self._websocket_manager.subscribe_market_data(
                exchange=exchange.value,
                ticker_symbol=ticker_symbol,
                callback=self._ws_marketdata_callback(key)
            )
            self._websocket_manager.subscribe_candles(
                exchange=exchange.value,
                ticker_symbol=ticker_symbol,
                timeframe=timeframe,
                callback=self._ws_candles_callback(key)
            )

    def shutdown(self):
        for asset in self._assets:
            self._websocket_manager.unsubscribe_market_data(
                exchange=asset.exchange.value,
                ticker_symbol=asset.ticker_symbol
            )
            self._websocket_manager.unsubscribe_candles(
                exchange=asset.exchange.value,
                ticker_symbol=asset.ticker_symbol,
                timeframe=asset.candles_timeframe
            )

    def _ws_marketdata_callback(self, asset_key: int):
        def _on_marketdata_update(new_market_data: MarketData):
            self.app_logger.debug(f"Market update: {asset_key} @ {new_market_data.close_price}")
            self._update_market_data(asset_key, new_market_data)

        return _on_marketdata_update

    def _update_market_data(self, asset_key: int, new_market_data: MarketData):
        current_market_data = self._market_data[asset_key]
        is_newer = current_market_data is None or current_market_data.timestamp < new_market_data.timestamp

        if is_newer:
            self._market_data[asset_key] = new_market_data
            self.app_logger.debug(f"Market data updated - Asset: {asset_key}, Price: {new_market_data.close_price}")
        else:
            self.app_logger.debug(f"Market data ignored (outdated) - Asset: {asset_key}")

    def get_market_data(self, asset: Asset) -> MarketData:
        market_data = self._market_data.get(asset.key)
        if market_data is None:
            provider = self.get_client(asset.exchange.value)
            new_market_data = provider.get_market_data(asset.ticker_symbol)
            self._update_market_data(asset.key, new_market_data)
            return self._market_data.get(asset.key)

        return market_data

    def _ws_candles_callback(self, asset_key: int):
        def _on_candles_update(new_candles: list[Candle]):
            self.app_logger.debug(f"Candles update: {asset_key} @ {new_candles}")
            self._update_candles(asset_key, new_candles)

        return _on_candles_update

    def _update_candles(self, asset_key: int, new_candles: list[Candle]) -> None:
        self._candles[asset_key].extend(new_candles)
        self._candles[asset_key].sort(key=lambda candle: candle.start_time)

        if len(self._candles[asset_key]) > self.MAX_CANDLES:
            excess = len(self._candles[asset_key]) - self.MAX_CANDLES
            del self._candles[asset_key][:excess]

    def get_candles(self, asset: Asset) -> list[Candle]:
        if len(self._candles[asset.key]) == 0:
            provider = self.get_client(asset.exchange.value)
            new_candles = provider.get_candles(asset.ticker_symbol, asset.candles_timeframe)
            self._update_candles(asset.key, new_candles)

        return self._candles[asset.key].copy()
