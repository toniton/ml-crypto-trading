from sqlalchemy import Column, Integer, String, TIMESTAMP

from database.database_manager import DatabaseManager


class OrderDao(DatabaseManager.BaseTableModel):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    uuid = Column(String, index=True, unique=True)
    provider_name = Column(String)
    ticker_symbol = Column(String)
    price = Column(String)
    quantity = Column(String)
    status = Column(String)
    trade_action = Column(String(4))
    last_updated_timestamp = Column(TIMESTAMP)
    created_timestamp = Column(TIMESTAMP)
