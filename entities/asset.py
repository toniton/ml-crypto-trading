#!/usr/bin/env python3

from pydantic import BaseModel


class Asset(BaseModel):
    keywords: tuple[str]
    ticker_symbol: str
    name: str
    asset_type: str
    current_price: float
    market_cap: float
    sector: str
    industry: str
