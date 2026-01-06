from datetime import datetime, timezone
from database.dao.order_dao import OrderDao
from api.interfaces.order import Order


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
            created_time=order_dao.created_timestamp.timestamp()
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
