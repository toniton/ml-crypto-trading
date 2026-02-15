from abc import ABC, abstractmethod
from typing import Any, List


class ExpressionContext(ABC):
    @abstractmethod
    def resolve_variable(self, name: str) -> Any:
        pass

    @abstractmethod
    def call_function(self, name: str, args: List[Any]) -> Any:
        pass
