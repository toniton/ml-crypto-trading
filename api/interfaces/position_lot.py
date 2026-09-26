from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import uuid4
from pydantic.dataclasses import dataclass


@dataclass
class PositionLot:
    lot_id: str
    order_uuid: str
    ticker_symbol: str
    price: Decimal
    quantity: Decimal
    remaining_quantity: Decimal
    fee_per_unit: Decimal
    timestamp: float
    winning_strategy: Optional[str] = None
    strategy_votes: Optional[dict[str, str]] = None

    @classmethod
    def create(
            cls,
            order_uuid: str,
            ticker_symbol: str,
            price: Decimal,
            quantity: Decimal,
            fee: Decimal,
            timestamp: float,
            lot_id: str | None = None,
            winning_strategy: Optional[str] = None,
            strategy_votes: Optional[dict[str, str]] = None,
    ) -> PositionLot:
        fee_per_unit = (fee / quantity) if quantity > Decimal(0) else Decimal(0)
        return cls(
            lot_id=lot_id or str(uuid4()),
            order_uuid=order_uuid,
            ticker_symbol=ticker_symbol,
            price=price,
            quantity=quantity,
            remaining_quantity=quantity,
            fee_per_unit=fee_per_unit,
            timestamp=timestamp,
            winning_strategy=winning_strategy,
            strategy_votes=strategy_votes,
        )
