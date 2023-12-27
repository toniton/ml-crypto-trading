#!/usr/bin/env python3

from pydantic import BaseModel

from entities.exchange_provider import ExchangeProvidersEnum


class Asset(BaseModel):
    keywords: list[str]
    ticker_symbol: str
    name: str
    asset_type: str
    current_price: float
    market_cap: float
    exchange: ExchangeProvidersEnum
    sector: str
    industry: str
