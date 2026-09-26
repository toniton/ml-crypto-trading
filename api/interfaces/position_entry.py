from decimal import Decimal
from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class PositionEntry:
    price: Decimal
    quantity: Decimal
    timestamp: float
