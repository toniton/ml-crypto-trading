from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
from pandas import DataFrame, Series
from sklearn.ensemble import RandomForestClassifier

from src.entities.asset import Asset
from src.entities.historical_data import HistoricalData
from prediction.helpers.random_forest_classifier_helper import RandomForestClassifierHelper
from prediction.models.prediction_model import PredictionModel


class RandomForestClassifierModel(PredictionModel):

    def __init__(self, asset: Asset, prediction_dir: str):
        self.asset = asset
        self.directory = Path(prediction_dir)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.predictors = ["Open", "High", "Low", "Close", "Volume"]
        self.model: RandomForestClassifier | None = None

    @staticmethod
    def convert_history_to_model(data: HistoricalData) -> Any:
        return data.model_dump().values()

    def get_filename(self) -> str:
        filename = f"{self.directory}/models/{self.asset.ticker_symbol.lower()}-random-forest.joblib"
        return filename

    def train_model(self, data: DataFrame, target: Series) -> None:
        helper = RandomForestClassifierHelper()
        self.model = helper.train_model(data, target)
        self.save_model()

    def save_model(self) -> None:
        filename = self.get_filename()
        joblib.dump(self.model, filename)

    def load_model(self) -> None:
        filename = self.get_filename()
        try:
            self.model = joblib.load(filename)
        except Exception as exc:
            raise Exception(["Unable to load model for the requested asset.", self.asset.name, exc])

    def predict(self, data: DataFrame) -> list[int]:
        if self.model:
            return self.model.predict(data)
        raise Exception(["You need to load or train model before prediction."])
