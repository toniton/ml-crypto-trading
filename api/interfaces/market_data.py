#!/usr/bin/env python3
from decimal import Decimal

from pydantic.dataclasses import dataclass


@dataclass
class MarketData:
    volume: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    timestamp: float
