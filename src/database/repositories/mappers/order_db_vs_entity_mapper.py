from datetime import datetime, timezone

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus
from src.database.dao.order_dao import OrderDao


class OrderDBVSEntityMapper:

    @staticmethod
    def map_to_entity(order_dao: OrderDao) -> Order:
        return Order(
            uuid=order_dao.uuid,
            provider_name=order_dao.provider_name,
            ticker_symbol=order_dao.ticker_symbol,
            price=order_dao.price,
            quantity=order_dao.quantity,
            trade_action=order_dao.trade_action,
            created_time=order_dao.created_timestamp.timestamp(),
            status=OrderStatus(order_dao.status) if order_dao.status else OrderStatus.PENDING,
        )

    @staticmethod
    def map_to_db(order: Order) -> OrderDao:
        created_datetime = datetime.fromtimestamp(order.created_time, tz=timezone.utc)
        return OrderDao(
            uuid=order.uuid,
            provider_name=order.provider_name,
            ticker_symbol=order.ticker_symbol,
            price=order.price,
            quantity=order.quantity,
            trade_action=order.trade_action.value,
            status=order.status.value,
            last_updated_timestamp=datetime.now(timezone.utc),
            created_timestamp=created_datetime
        )
