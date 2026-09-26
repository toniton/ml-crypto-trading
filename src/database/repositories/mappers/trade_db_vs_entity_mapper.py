from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from api.interfaces.trade import Trade
from src.database.dao.trade_dao import TradeDao


class TradeDBVSEntityMapper:
    @staticmethod
    def map_to_db(trade: Trade) -> TradeDao:
        entry_dt = datetime.fromtimestamp(trade.entry_timestamp, tz=timezone.utc)
        exit_dt = datetime.fromtimestamp(trade.exit_timestamp, tz=timezone.utc)
        trade_metadata = {
            "commit_hash": trade.commit_hash,
            "winning_strategy": trade.winning_strategy,
            "strategy_votes": trade.strategy_votes,
        }
        return TradeDao(
            trade_id=trade.trade_id,
            ticker_symbol=trade.ticker_symbol,
            entry_order_uuid=trade.entry_order_uuid,
            exit_order_uuid=trade.exit_order_uuid,
            entry_price=str(trade.entry_price),
            exit_price=str(trade.exit_price),
            quantity=str(trade.quantity),
            gross_pnl=str(trade.gross_pnl),
            fees=str(trade.fees),
            slippage=str(trade.slippage) if trade.slippage is not None else "0",
            net_pnl=str(trade.net_pnl),
            return_pct=str(trade.return_pct),
            duration_seconds=float(trade.duration_seconds),
            entry_timestamp=entry_dt,
            exit_timestamp=exit_dt,
            metadata_=trade_metadata,
        )

    @staticmethod
    def map_to_entity(dao: Optional[TradeDao]) -> Optional[Trade]:
        if dao is None:
            return None

        entry_ts = dao.entry_timestamp.timestamp() if dao.entry_timestamp else 0.0
        exit_ts = dao.exit_timestamp.timestamp() if dao.exit_timestamp else 0.0
        metadata = dao.metadata_ if isinstance(dao.metadata_, dict) else {}
        return Trade(
            trade_id=dao.trade_id,
            ticker_symbol=dao.ticker_symbol,
            entry_order_uuid=dao.entry_order_uuid,
            exit_order_uuid=dao.exit_order_uuid,
            entry_price=Decimal(str(dao.entry_price)),
            exit_price=Decimal(str(dao.exit_price)),
            quantity=Decimal(str(dao.quantity)),
            gross_pnl=Decimal(str(dao.gross_pnl)),
            fees=Decimal(str(dao.fees)),
            slippage=Decimal(str(dao.slippage or "0")),
            net_pnl=Decimal(str(dao.net_pnl)),
            return_pct=Decimal(str(dao.return_pct)),
            duration_seconds=float(dao.duration_seconds or 0.0),
            entry_timestamp=entry_ts,
            exit_timestamp=exit_ts,
            commit_hash=metadata.get("commit_hash"),
            winning_strategy=metadata.get("winning_strategy"),
            strategy_votes=metadata.get("strategy_votes"),
        )
