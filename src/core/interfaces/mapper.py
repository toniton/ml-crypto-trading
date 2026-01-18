from abc import ABC, abstractmethod
from typing import TypeVar, Generic

T = TypeVar("T")
R = TypeVar("R")


class Mapper(ABC, Generic[T, R]):
    @abstractmethod
    def map(self, source: T) -> R:
        pass
