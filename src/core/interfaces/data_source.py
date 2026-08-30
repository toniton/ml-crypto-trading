from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")
D = TypeVar("D")


class DataSource(ABC, Generic[T, D]):
    @abstractmethod
    def load(self, request: T) -> D:
        pass
