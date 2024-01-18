from __future__ import annotations

import abc
from abc import ABC

from pandas import DataFrame, Series


class PredictionModel(ABC):

    @abc.abstractmethod
    def train_model(self, data: DataFrame, target: Series) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def save_model(self) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def load_model(self) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def predict(self, data: DataFrame) -> list[int]:
        raise NotImplementedError()
