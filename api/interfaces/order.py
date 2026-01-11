#!/usr/bin/env python3
from decimal import Decimal
from typing import Optional

from pydantic import RootModel
from pydantic.dataclasses import dataclass

from api.interfaces.trade_action import OrderStatus, TradeAction


@dataclass
class Order:
    uuid: str
    provider_name: str
    ticker_symbol: str
    price: Decimal
    quantity: str
    trade_action: TradeAction
    created_time: float
    status: Optional[OrderStatus] = OrderStatus.PENDING

    def model_dump_json(self) -> str:
        return RootModel[Order](self).model_dump_json()
