from sqlalchemy import Column, Integer, String, TIMESTAMP

from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class OrderDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    uuid = Column(String, index=True, unique=True)
    provider_name = Column(String)
    ticker_symbol = Column(String)
    price = Column(String)
    quantity = Column(String)
    status = Column(String)
    trade_action = Column(String(4))
    commit_hash = Column(String, nullable=True)
    fees = Column(String, nullable=True)
    fill_price = Column(String, nullable=True)
    last_updated_timestamp = Column(TIMESTAMP)
    created_timestamp = Column(TIMESTAMP)
    executed_timestamp = Column(TIMESTAMP)
