from database.dao.order_dao import OrderDao
from entities.order import Order


class OrderDBVSEntityMapper:

    @staticmethod
    def map_to_entity(order_dao: OrderDao) -> Order:
        return Order(
            uuid=order_dao.uuid,
            provider_name=order_dao.provider_name,
            ticker_symbol=order_dao.ticker_symbol,
            price=order_dao.price,
            quantity=order_dao.quantity,
            trade_action=order_dao.trade_action
        )

    @staticmethod
    def map_to_db(order: Order) -> OrderDao:
        return OrderDao(
            uuid=order.uuid,
            provider_name=order.provider_name,
            ticker_symbol=order.ticker_symbol,
            price=order.price,
            quantity=order.quantity,
            trade_action=order.trade_action.value,
        )
