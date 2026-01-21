#!/usr/bin/env python3
from decimal import Decimal

from pydantic import BaseModel

from api.interfaces.asset import Asset


class HistoricalData(BaseModel):
    asset: Asset
    year_week: str
    timestamp: str
    open_price: Decimal
    close_price: Decimal
    high_price: Decimal
    low_price: Decimal
    volume: int
