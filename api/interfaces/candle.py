from decimal import Decimal

from pydantic.dataclasses import dataclass


@dataclass
class Candle:
    open: Decimal
    low: Decimal
    high: Decimal
    close: Decimal
    start_time: float
