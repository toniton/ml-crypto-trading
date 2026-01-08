from typing import cast

from sqlalchemy.dialects.postgresql import insert

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus
from database.dao.order_dao import OrderDao
from database.repositories.mappers.order_db_vs_entity_mapper import OrderDBVSEntityMapper
from database.repositories.order_repository import OrderRepository


class PostgresOrderRepository(OrderRepository):
    TERMINAL_STATUSES = {
        OrderStatus.COMPLETED.value,
        OrderStatus.CANCELLED.value
    }

    def save(self, order: Order):
        order_dao = OrderDBVSEntityMapper.map_to_db(order)
        self.database_session.add(order_dao)

    def get(self, order_id: str):
        self.database_session.query(OrderDao).filter(OrderDao.uuid == order_id)

    def get_all(self):
        pass

    def update(self, order_id, order):
        pass

    def upsert(self, order: Order) -> None:
        order_dao = OrderDBVSEntityMapper.map_to_db(order)
        insert_statement = insert(OrderDao).values(
            uuid=order_dao.uuid,
            provider_name=order_dao.provider_name,
            ticker_symbol=order_dao.ticker_symbol,
            price=order_dao.price,
            quantity=order_dao.quantity,
            trade_action=order_dao.trade_action,
            status=order_dao.status,
            last_updated_timestamp=order_dao.last_updated_timestamp,
            created_timestamp=order_dao.created_timestamp
        )
        upsert_statement = insert_statement.on_conflict_do_update(
            index_elements=["uuid"],
            where=OrderDao.status.notin_(self.TERMINAL_STATUSES),
            set_={
                OrderDao.price: order_dao.price,
                OrderDao.ticker_symbol: order_dao.ticker_symbol,
                OrderDao.status: order_dao.status,
                OrderDao.last_updated_timestamp: order_dao.last_updated_timestamp
            },
        )
        self.database_session.execute(upsert_statement)

    def get_by_exchange(self, customer_id):
        return 5

    def get_by_ticker_symbol(self, product_id):
        pass

    def get_by_date(self, date):
        pass

    def get_by_status(self, status: OrderStatus):
        query = self.database_session.query(OrderDao)
        filtered_query = query.filter(OrderDao.status.in_([status.value]))
        results = list(map(OrderDBVSEntityMapper.map_to_entity, filtered_query.all()))
        return results

    def get_by_price(self, ticker_symbol: str, price: str) -> list[Order]:
        result = []
        query = self.database_session.query(OrderDao)
        filtered_query = query.filter(
            OrderDao.price > price,
            OrderDao.ticker_symbol == ticker_symbol
        )
        for order_dao in filtered_query:
            result.append(OrderDBVSEntityMapper.map_to_entity(cast(OrderDao, order_dao)))
        return result
