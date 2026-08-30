from decimal import Decimal
from typing import Protocol


class FeeModel(Protocol):
    def calculate(self, notional: Decimal) -> Decimal:
        ...
