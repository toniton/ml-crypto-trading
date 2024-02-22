from typing import cast
from uuid import UUID

from database.dao.order_dao import OrderDao
from entities.order import Order
from database.repositories.mappers.order_db_vs_entity_mapper import OrderDBVSEntityMapper
from database.repositories.order_repository import OrderRepository


class PostgresOrderRepository(OrderRepository):
    def save(self, order: Order):
        order_dao = OrderDBVSEntityMapper.map_to_db(order)
        self.database_session.add(order_dao)

    def get(self, order_id: UUID):
        self.database_session.query(OrderDao).filter(OrderDao.uuid == str(order_id))

    def get_all(self):
        pass

    def update(self, order_id, order):
        pass

    def get_by_exchange(self, customer_id):
        return 5

    def get_by_ticker_symbol(self, product_id):
        pass

    def get_by_date(self, date):
        pass

    def get_by_status(self, status):
        pass

    def get_by_price(self, ticker_symbol: str, price: str) -> list[Order]:
        result = []
        query = self.database_session.query(OrderDao)
        filtered_query = query.filter(
            OrderDao.price > price,
            OrderDao.ticker_symbol == ticker_symbol
        )
        for orderDao in filtered_query:
            result.append(OrderDBVSEntityMapper.map_to_entity(cast(OrderDao, orderDao)))
        return result
