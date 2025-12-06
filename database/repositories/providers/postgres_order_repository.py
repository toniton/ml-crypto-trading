from typing import cast

from sqlalchemy.dialects.postgresql import insert

from database.dao.order_dao import OrderDao
from api.interfaces.order import Order
from database.repositories.mappers.order_db_vs_entity_mapper import OrderDBVSEntityMapper
from database.repositories.order_repository import OrderRepository


class PostgresOrderRepository(OrderRepository):
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
        insert_statement = insert(OrderDao).values(
            uuid=order.uuid,
            provider_name=order.provider_name,
            ticker_symbol=order.ticker_symbol,
            price=order.price,
            quantity=order.quantity,
            trade_action=str(order.trade_action.value),
            status=str(order.status.value),
        )
        upsert_statement = insert_statement.on_conflict_do_update(
            index_elements=["uuid"],
            set_={
                OrderDao.price: order.price,
                OrderDao.ticker_symbol: order.ticker_symbol,
                OrderDao.status: str(order.status.value),
            },
        )
        self.database_session.execute(upsert_statement)

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
