#!/usr/bin/env python3
from uuid import UUID

from pydantic import RootModel
from pydantic.dataclasses import dataclass

from api.interfaces.trade_action import TradeAction


@dataclass
class Order:
    uuid: UUID
    provider_name: str
    ticker_symbol: str
    price: str
    quantity: str
    trade_action: TradeAction

    def model_dump_json(self) -> str:
        return RootModel[Order](self).model_dump_json()
