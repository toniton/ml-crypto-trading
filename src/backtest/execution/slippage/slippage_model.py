from decimal import Decimal
from typing import Protocol

from api.interfaces.asset import Asset
from api.interfaces.trade_action import TradeAction


class SlippageModel(Protocol):
    def apply(self, trade_action: TradeAction, price: Decimal, asset: Asset) -> Decimal:
        ...
