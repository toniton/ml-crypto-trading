
from sqlalchemy import Column, Integer, String, TIMESTAMP, UUID, func

from database.database_setup import DatabaseSetup


class OrderDao(DatabaseSetup.BaseTableModel):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    uuid = Column(UUID(as_uuid=True), index=True, unique=True)
    provider_name = Column(String)
    ticker_symbol = Column(String)
    price = Column(String)
    quantity = Column(String)
    status = Column(String)
    trade_action = Column(String(4))
    last_updated_time = Column(TIMESTAMP, default=None)
    created_time = Column(TIMESTAMP, default=func.current_timestamp())
