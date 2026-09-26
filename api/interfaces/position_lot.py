from __future__ import annotations

from decimal import Decimal
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
        )
