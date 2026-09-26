from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import uuid4
from pydantic.dataclasses import dataclass


# pylint: disable=too-many-instance-attributes,too-many-arguments,too-many-positional-arguments,too-many-locals
@dataclass(frozen=True)
class Trade:
    trade_id: str
    ticker_symbol: str
    entry_order_uuid: str
    exit_order_uuid: str
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    gross_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal
    return_pct: Decimal
    duration_seconds: float
    entry_timestamp: float
    exit_timestamp: float
    slippage: Decimal = Decimal(0)
    commit_hash: Optional[str] = None

    @classmethod
    def create(
            cls,
            ticker_symbol: str,
            entry_order_uuid: str,
            exit_order_uuid: str,
            entry_price: Decimal,
            exit_price: Decimal,
            quantity: Decimal,
            entry_fee: Decimal,
            exit_fee: Decimal,
            entry_timestamp: float,
            exit_timestamp: float,
            slippage: Decimal = Decimal(0),
            commit_hash: Optional[str] = None,
            trade_id: Optional[str] = None,
    ) -> Trade:
        gross_pnl = (exit_price - entry_price) * quantity
        total_fees = entry_fee + exit_fee
        net_pnl = gross_pnl - total_fees - slippage
        cost_basis = (entry_price * quantity) + entry_fee
        return_pct = (net_pnl / cost_basis * Decimal(100)) if cost_basis > Decimal(0) else Decimal(0)
        duration_seconds = max(0.0, exit_timestamp - entry_timestamp)

        return cls(
            trade_id=trade_id or str(uuid4()),
            ticker_symbol=ticker_symbol,
            entry_order_uuid=entry_order_uuid,
            exit_order_uuid=exit_order_uuid,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            gross_pnl=gross_pnl,
            fees=total_fees,
            slippage=slippage,
            net_pnl=net_pnl,
            return_pct=return_pct,
            duration_seconds=duration_seconds,
            entry_timestamp=entry_timestamp,
            exit_timestamp=exit_timestamp,
            commit_hash=commit_hash,
        )
