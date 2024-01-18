#!/usr/bin/env python3
from uuid import UUID

from pydantic import BaseModel

from entities.trade_action import TradeAction


class Order(BaseModel):
    uuid: UUID
    provider_name: str
    ticker_symbol: str
    price: str
    quantity: str
    trade_action: TradeAction
