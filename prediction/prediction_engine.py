from __future__ import annotations

import datetime
import logging

import pandas as pd
import schedule
from pandas import DataFrame

from entities.asset import Asset
from entities.market_data import MarketData
from prediction.models.random_forest_classifier_model import RandomForestClassifierModel
from prediction.models.prediction_model import PredictionModel
from prediction.preprocessors.coinmarketcap_preprocessor import CoinMarketCapPreProcessor
from prediction.providers.history_data_provider import HistoryDataProvider
from prediction.providers.local_storage_data_provider import LocalStorageDataProvider


class PredictionEngine:
    def __init__(self, assets: list[Asset]):
        self.history_cache: dict[str, DataFrame] = {}
        self.asset_lookup: dict[str, Asset] = {}
        self.data_provider: HistoryDataProvider = LocalStorageDataProvider()
        self.models: dict[str, PredictionModel] = {}
        self.assets = assets
        self.init_application()
        self.preprocessor = CoinMarketCapPreProcessor()

    def init_application(self):
        for asset in self.assets:
            try:
                self.models[asset.ticker_symbol] = RandomForestClassifierModel(asset)
                self.asset_lookup[asset.ticker_symbol] = asset
                data = self.data_provider.get_ticker_data(asset.ticker_symbol)
                self.history_cache[asset.ticker_symbol] = data.head(1200).copy()
            except Exception as exc:
                logging.error(["Error occurred initializing application. ->", exc])

    def start_training(self):
        try:
            schedule.every().week.do(self.train_assets_model())
            # schedule.every().day.do(self.update_data_source(assets))
        except Exception as exc:
            logging.error(["Error occurred initializing application. ->", exc])

    def set_data_provider(self, data_provider: HistoryDataProvider):
        self.data_provider = data_provider

    def load_assets_model(self):
        for asset in self.assets:
            try:
                self.models[asset.ticker_symbol].load_model()
            except Exception as exc:
                logging.error([f"Error occurred loading asset: {asset.name}. ->", exc])

    def train_assets_model(self):
        for asset in self.assets:
            data = self.data_provider.get_ticker_data(asset.ticker_symbol)

            (processed_data, predictors) = self.preprocessor.pre_process_data(data)

            prediction_model = self.models[asset.ticker_symbol]

            target = processed_data.Target
            filtered_data = processed_data[predictors].values

            prediction_model.train_model(filtered_data, target)

    def predict(self, ticker_symbol: str, current_data: MarketData) -> int:
        if self.models[ticker_symbol]:
            history_cache = self.history_cache[ticker_symbol]
            asset = self.asset_lookup[ticker_symbol]

            date_utc_now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            combined_data = pd.concat([
                pd.DataFrame({
                    'timeOpen': [date_utc_now],
                    'timeClose': [date_utc_now],
                    'timeHigh': [date_utc_now],
                    'timeLow': [date_utc_now],
                    'name': [asset.name],
                    'open': [current_data.low_price],
                    'high': [current_data.high_price],
                    'low': [current_data.low_price],
                    'close': [float(current_data.close_price)],
                    'volume': [current_data.volume],
                    'marketCap': [asset.market_cap],
                    'timestamp': [datetime.datetime.utcfromtimestamp(current_data.timestamp / 1000).strftime('%Y-%m-%dT%H:%M:%S.%fZ')]
                }),
                history_cache
            ], ignore_index=True)

            (processed_data, predictors) = self.preprocessor.pre_process_data(combined_data)

            filtered_data = processed_data[predictors].values

            predictions = self.models[ticker_symbol].predict(filtered_data)

            # self.history_cache[ticker_symbol] = combined_data.head(1200).copy()

            return predictions[0]

        raise ValueError(
            f"Model for {ticker_symbol} ticker not found in prediction engine. "
            f"Load assets model and try again."
        )

    # def fine_tune_model(self, ticker_symbol: str):
    #     today = datetime.datetime.now()
    #     last_7_days = today - datetime.timedelta(days=7)
    #     try:
    #         history_data = self.data_provider.get_ticker_data(ticker_symbol, last_7_days, today)
    #         self.models[ticker_symbol].fine_tune_model(history_data)
    #     except Exception as exc:
    #         raise ValueError(
    #             f"Error occurred fine-tuning model for {ticker_symbol} ticker not found in prediction engine. {exc}"
    #         )
    #
    # def update_data_source(self, assets):
    #     today = datetime.datetime.now()
    #     last_7_days = today - datetime.timedelta(days=7)
    #     for asset in assets:
    #         try:
    #             history_data = self.data_provider.get_ticker_data(asset.ticker_symbol, last_7_days, today)
    #             self.models[asset.ticker_symbol].fine_tune_model(history_data)
    #         except Exception as exc:
    #             raise ValueError(
    #                 f"Error occurred fine-tuning model for {asset.ticker_symbol} ticker not found in prediction engine. {exc}"
    #             )
    #     pass
