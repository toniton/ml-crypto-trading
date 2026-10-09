from __future__ import annotations

from decimal import Decimal
from typing import Optional

from api.interfaces.position_lot import PositionLot
from api.interfaces.trade import Trade


class FifoTradeMatcher:

    @staticmethod
    def match_lots(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
            lots: list[PositionLot],
            ticker_symbol: str,
            exit_order_uuid: str,
            exit_price: Decimal,
            exit_quantity: Decimal,
            exit_fee: Decimal,
            exit_timestamp: float,
            commit_hash: Optional[str] = None,
            winning_strategy: Optional[str] = None,
            strategy_votes: Optional[dict[str, str]] = None,
            strategy_attributions: Optional[dict[str, float]] = None,
            exit_slippage: Decimal = Decimal(0),
    ) -> tuple[list[Trade], Decimal]:
        completed_trades: list[Trade] = []
        sell_remaining = exit_quantity
        sell_fee_per_unit = (exit_fee / exit_quantity) if exit_quantity > Decimal(0) else Decimal(0)
        exit_slippage_per_unit = (exit_slippage / exit_quantity) if exit_quantity > Decimal(0) else Decimal(0)

        while sell_remaining > Decimal(0) and lots:
            lot = lots[0]
            matched_qty = min(sell_remaining, lot.remaining_quantity)
            entry_slippage_portion = lot.slippage_per_unit * matched_qty
            exit_slippage_portion = exit_slippage_per_unit * matched_qty
            total_matched_slippage = entry_slippage_portion + exit_slippage_portion

            trade = Trade.create(
                ticker_symbol=ticker_symbol,
                entry_order_uuid=lot.order_uuid,
                exit_order_uuid=exit_order_uuid,
                entry_price=lot.price,
                exit_price=exit_price,
                quantity=matched_qty,
                entry_fee=lot.fee_per_unit * matched_qty,
                exit_fee=sell_fee_per_unit * matched_qty,
                entry_timestamp=lot.timestamp,
                exit_timestamp=exit_timestamp,
                slippage=total_matched_slippage,
                commit_hash=commit_hash,
                winning_strategy=lot.winning_strategy or winning_strategy,
                strategy_votes=lot.strategy_votes or strategy_votes,
                entry_strategy_attributions=lot.strategy_attributions,
                exit_strategy_attributions=strategy_attributions,
                exit_winning_strategy=winning_strategy,
            )
            completed_trades.append(trade)

            lot.remaining_quantity -= matched_qty
            sell_remaining -= matched_qty
            if lot.remaining_quantity <= Decimal(0):
                lots.pop(0)

        return completed_trades, sell_remaining
