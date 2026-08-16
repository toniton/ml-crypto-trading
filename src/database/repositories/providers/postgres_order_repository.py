from typing import cast

from sqlalchemy.dialects.postgresql import insert

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus
from src.database.dao.order_dao import OrderDao
from src.database.repositories.mappers.order_db_vs_entity_mapper import OrderDBVSEntityMapper
from src.database.repositories.order_repository import OrderRepository


class PostgresOrderRepository(OrderRepository):
    TERMINAL_STATUSES = {
        OrderStatus.COMPLETED.value,
        OrderStatus.CANCELLED.value
    }

    def save(self, entity: Order):
        order_dao = OrderDBVSEntityMapper.map_to_db(entity)
        self.database_session.add(order_dao)

    def get(self, entity_id: str):
        self.database_session.query(OrderDao).filter(OrderDao.uuid == entity_id)

    def get_all(self):
        pass

    def update(self, entity_id, entity):
        pass

    def upsert(self, entity: Order) -> None:
        order_dao = OrderDBVSEntityMapper.map_to_db(entity)
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

    def get_by_exchange(self, exchange_name):
        return self.database_session.query(OrderDao).filter(OrderDao.provider_name == exchange_name).all()

    def get_by_ticker_symbol(self, ticker_symbol):
        return self.database_session.query(OrderDao).filter(OrderDao.ticker_symbol == ticker_symbol).all()

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
