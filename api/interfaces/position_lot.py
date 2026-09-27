from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import uuid4
from pydantic.dataclasses import dataclass


# pylint: disable=too-many-arguments,too-many-positional-arguments
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
    slippage_per_unit: Decimal = Decimal(0)
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
            slippage: Decimal = Decimal(0),
            slippage_per_unit: Optional[Decimal] = None,
    ) -> PositionLot:
        computed_fee_per_unit = (fee / quantity) if quantity > Decimal(0) else Decimal(0)
        computed_slippage_per_unit = (
            slippage_per_unit
            if slippage_per_unit is not None
            else ((slippage / quantity) if quantity > Decimal(0) else Decimal(0))
        )
        return cls(
            lot_id=lot_id or str(uuid4()),
            order_uuid=order_uuid,
            ticker_symbol=ticker_symbol,
            price=price,
            quantity=quantity,
            remaining_quantity=quantity,
            fee_per_unit=computed_fee_per_unit,
            timestamp=timestamp,
            slippage_per_unit=computed_slippage_per_unit,
            winning_strategy=winning_strategy,
            strategy_votes=strategy_votes,
        )
