from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from src.core.interfaces.exchange_rest_builder import ExchangeRestBuilder

T = TypeVar('T', bound=BaseModel)
R = TypeVar('R')


class ExchangeRestService(ABC):

    @abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abstractmethod
    def execute(self, builder: ExchangeRestBuilder[T, R]) -> R:
        pass

    @abstractmethod
    def builder(self) -> ExchangeRestBuilder[T, R]:
        pass
