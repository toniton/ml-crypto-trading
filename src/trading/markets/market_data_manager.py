from __future__ import annotations

import threading
from typing import List

from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from src.clients.rest_manager import RestManager
from src.clients.websocket_manager import WebSocketManager
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin


class MarketDataManager(ApplicationLoggingMixin):
    MAX_CANDLES = 50

    def __init__(self, rest_manager: RestManager, websocket_manager: WebSocketManager):
        self._rest_manager = rest_manager
        self._websocket_manager = websocket_manager
        self._assets: list[Asset] = []
        self._market_data: dict[int, MarketData | None] = {}
        self._candles: dict[int, list[Candle]] = {}
        self._lock = threading.Lock()

    def get_rest_market_data(self, exchange: str, ticker_symbol: str) -> MarketData:
        return self._rest_manager.get_market_data(exchange, ticker_symbol)

    def get_rest_candles(self, exchange: str, ticker_symbol: str, timeframe: Timeframe) -> List[Candle]:
        return self._rest_manager.get_candles(exchange, ticker_symbol, timeframe)

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
        with self._lock:
            current_market_data = self._market_data.get(asset_key)
            is_newer = current_market_data is None or current_market_data.timestamp < new_market_data.timestamp

            if is_newer:
                self._market_data[asset_key] = new_market_data
                self.app_logger.debug(f"Market data updated - Asset: {asset_key}, Price: {new_market_data.close_price}")
            else:
                self.app_logger.debug(f"Market data ignored (outdated) - Asset: {asset_key}")

    def get_market_data(self, asset: Asset) -> MarketData:
        with self._lock:
            market_data = self._market_data.get(asset.key)

        if market_data is None:
            new_market_data = self.get_rest_market_data(asset.exchange.value, asset.ticker_symbol)
            self._update_market_data(asset.key, new_market_data)
            with self._lock:
                return self._market_data.get(asset.key)

        return market_data

    def _ws_candles_callback(self, asset_key: int):
        def _on_candles_update(new_candles: list[Candle]):
            self.app_logger.debug(f"Candles update: {asset_key} @ {new_candles}")
            self._update_candles(asset_key, new_candles)

        return _on_candles_update

    def _update_candles(self, asset_key: int, new_candles: list[Candle]) -> None:
        with self._lock:
            if asset_key not in self._candles:
                self._candles[asset_key] = []

            self._candles[asset_key].extend(new_candles)
            self._candles[asset_key].sort(key=lambda candle: candle.start_time)

            if len(self._candles[asset_key]) > self.MAX_CANDLES:
                excess = len(self._candles[asset_key]) - self.MAX_CANDLES
                del self._candles[asset_key][:excess]

    def get_candles(self, asset: Asset) -> list[Candle]:
        with self._lock:
            candles_exist = len(self._candles.get(asset.key, [])) > 0

        if not candles_exist:
            new_candles = self.get_rest_candles(asset.exchange.value, asset.ticker_symbol, asset.candles_timeframe)
            self._update_candles(asset.key, new_candles)

        with self._lock:
            return self._candles.get(asset.key, []).copy()
