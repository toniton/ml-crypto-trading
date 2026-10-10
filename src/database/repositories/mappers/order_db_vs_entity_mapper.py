from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.database.dao.order_dao import OrderDao


class OrderDBVSEntityMapper:

    @staticmethod
    def map_to_entity(order_dao: OrderDao) -> Order:
        metadata = order_dao.metadata_ if isinstance(order_dao.metadata_, dict) else {}
        strategy_votes = metadata.get("strategy_votes")
        strategy_attributions = metadata.get("strategy_attributions")

        return Order(
            uuid=order_dao.uuid,
            provider_name=order_dao.provider_name,
            ticker_symbol=order_dao.ticker_symbol,
            price=Decimal(order_dao.price),
            quantity=order_dao.quantity,
            trade_action=TradeAction(order_dao.trade_action),
            created_time=order_dao.created_timestamp.replace(tzinfo=timezone.utc).timestamp(),
            commit_hash=order_dao.commit_hash,
            executed_time=(
                order_dao.executed_timestamp.replace(tzinfo=timezone.utc).timestamp()
                if order_dao.executed_timestamp
                else None
            ),
            status=OrderStatus(order_dao.status) if order_dao.status else OrderStatus.PENDING,
            fees=Decimal(order_dao.fees) if order_dao.fees is not None else None,
            fill_price=Decimal(order_dao.fill_price) if order_dao.fill_price is not None else None,
            decision_id=order_dao.decision_id,
            winning_strategy=metadata.get("winning_strategy"),
            strategy_votes=strategy_votes if isinstance(strategy_votes, dict) else None,
            strategy_attributions=(
                strategy_attributions if isinstance(strategy_attributions, dict) else None
            ),
        )

    @staticmethod
    def map_to_db(order: Order) -> OrderDao:
        created_datetime = datetime.fromtimestamp(order.created_time, tz=timezone.utc)
        executed_datetime = (
            datetime.fromtimestamp(order.executed_time, tz=timezone.utc)
            if order.executed_time is not None
            else None
        )
        metadata: dict[str, Any] = {}
        if order.winning_strategy is not None:
            metadata["winning_strategy"] = order.winning_strategy
        if order.strategy_votes is not None:
            metadata["strategy_votes"] = order.strategy_votes
        if order.strategy_attributions is not None:
            metadata["strategy_attributions"] = order.strategy_attributions

        return OrderDao(
            uuid=order.uuid,
            provider_name=order.provider_name,
            ticker_symbol=order.ticker_symbol,
            price=str(order.price),
            quantity=order.quantity,
            trade_action=order.trade_action.value,
            status=order.status.value,
            commit_hash=order.commit_hash,
            decision_id=order.decision_id,
            fees=str(order.fees) if order.fees is not None else None,
            fill_price=str(order.fill_price) if order.fill_price is not None else None,
            last_updated_timestamp=datetime.now(timezone.utc),
            created_timestamp=created_datetime,
            executed_timestamp=executed_datetime,
            metadata_=metadata if metadata else None,
        )
