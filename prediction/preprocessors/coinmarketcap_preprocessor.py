import logging

import pandas as pd
from pandas import DataFrame

from prediction.preprocessors.preprocessor import PreProcessor


class CoinMarketCapPreProcessor(PreProcessor):
    predictors = ["Open", "High", "Low", "Close"]
    horizons = [10, 50, 100, 250, 500, 1000]

    @classmethod
    def get_horizon(cls, training_data: DataFrame, predictors: list[str]) -> tuple[DataFrame, list]:
        for horizon in cls.horizons:
            if horizon < training_data.shape[0]:
                rolling_averages = training_data["Close"].rolling(window=horizon, min_periods=1).mean()
                rolling_sums = training_data["Target"].rolling(window=horizon, min_periods=1).sum()

                ratio_column = f"Close_Ratio_{horizon}"
                training_data[ratio_column] = training_data["Close"] / rolling_averages

                trend_column = f"Trend_{horizon}"
                training_data[trend_column] = rolling_sums
                # = .shift(1)

                predictors.extend([ratio_column, trend_column])
            else:
                logging.warning(f"Horizon {horizon} exceeds data size.")
        return training_data, predictors

    def pre_process_data(self, data: DataFrame) -> tuple[DataFrame, list[str]]:
        data.rename(columns={
            'open': "Open", 'high': "High",
            'low': "Low", 'close': "Close",
            # 'volume': "Volume",
            'timestamp': "Date"
        }, inplace=True)
        data['Date'] = pd.to_datetime(data['Date'], utc=True)
        data["Tomorrow"] = data["Close"].shift(-1)
        data["Target"] = (data["Tomorrow"] > data["Close"]).apply(int)
        clean_data = data.drop(data.index[-1])

        predictors_copy = self.predictors.copy()
        clean_data, predictors = self.get_horizon(clean_data, predictors_copy)
        return clean_data, predictors
