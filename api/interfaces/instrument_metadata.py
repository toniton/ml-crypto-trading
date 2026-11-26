from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class InstrumentMetadata:
    """Exchange-reported order sizing and precision constraints for a trading instrument."""

    exchange: str
    symbol: str
    quantity_precision: int
    price_precision: int
    min_quantity: Decimal
    quantity_step: Decimal
    min_price: Optional[Decimal] = None
    min_notional: Optional[Decimal] = None
