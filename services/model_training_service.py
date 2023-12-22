from typing import List
import pandas as pd
from pandas import DataFrame
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score
import logging


class ModelTrainingService:
    logger = None
    n_estimators = 200
    min_samples_split = 150
    random_state = 1

    def __init__(self, n_estimators: int, min_samples_split: int, random_state: int):
        print(n_estimators, min_samples_split)
        self.n_estimators = n_estimators
        self.min_samples_split = min_samples_split
        self.random_state = random_state
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _get_horizon(training_data: DataFrame, predictors: List) -> tuple[DataFrame, list]:
        horizons = [2, 5, 60, 250, 1000]
        for horizon in horizons:
            if horizon < training_data.shape[0]:
                rolling_averages = training_data["Close"].rolling(window=horizon).mean()
                rolling_sums = training_data["Target"].rolling(window=horizon).sum()

                ratio_column = f"Close_Ratio_{horizon}"
                training_data[ratio_column] = training_data["Close"] / rolling_averages

                trend_column = f"Trend_{horizon}"
                training_data[trend_column] = rolling_sums.shift(1)

                predictors.extend([ratio_column, trend_column])
            else:
                ModelTrainingService.logger.warning(f"Horizon {horizon} exceeds data size.")
        return training_data, predictors

    @staticmethod
    def _predict(training_data, test, predictors, model):
        model.fit(training_data[predictors], training_data["Target"])
        preds = model.predict_proba(test[predictors])[:, 1]
        preds[preds >= .6] = 1
        preds[preds <= .6] = 0
        preds = pd.Series(preds, index=test.index, name="Predictions")
        combined = pd.concat([test["Target"], preds], axis=1)
        return combined

    @staticmethod
    def _backtest(training_data, model, predictors, start=10, step=15):
        all_predictions = []
        # print(start, training_data.shape, step)
        for i in range(start, training_data.shape[0], step):
            train = training_data.iloc[0:i].copy()
            test = training_data.iloc[i:(i + step)].copy()
            predictions = ModelTrainingService._predict(train, test, predictors, model)
            all_predictions.append(predictions)
        return pd.concat(all_predictions)

    def train_model(
            self,
            training_data: DataFrame,
            predictors: List[str],
            limit: int = 100
    ) -> tuple[RandomForestClassifier, int]:
        model = RandomForestClassifier(
            n_estimators=self.n_estimators,
            min_samples_split=self.min_samples_split,
            random_state=self.random_state
        )

        # max_length = training_data.size

        # if max_length < limit:
        #     limit = max_length / 2
        # Optional add horizon
        training_data, predictors = ModelTrainingService._get_horizon(training_data, predictors)
        training_data = training_data.dropna()

        print(training_data.to_markdown(tablefmt="grid"))

        predictions = ModelTrainingService._backtest(training_data, model, predictors)
        predictions["Predictions"].value_counts()
        # print(predictions.to_markdown(tablefmt="grid"))

        score = precision_score(predictions["Target"], predictions["Predictions"])
        print(f"Precision score: {score}")
        return model, score
