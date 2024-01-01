#!/usr/bin/env python3
from pydantic import BaseModel


class MarketData(BaseModel):
    close_price: float
