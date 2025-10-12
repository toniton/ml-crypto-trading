#!/usr/bin/env python3

from pydantic import BaseModel

from api.interfaces.asset import Asset


class HistoricalData(BaseModel):
    asset: Asset
    year_week: str
    timestamp: str
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    volume: int
