from sqlalchemy import Column, Float, Integer, String, TIMESTAMP

from src.database.dao.blob_dao import JSON_TYPE
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class TradeDao(SqlAlchemyDatabaseManager.BaseTableModel):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    trade_id = Column(String, index=True, unique=True)
    ticker_symbol = Column(String, index=True)
    entry_order_uuid = Column(String, index=True)
    exit_order_uuid = Column(String, index=True)
    entry_price = Column(String)
    exit_price = Column(String)
    quantity = Column(String)
    gross_pnl = Column(String)
    fees = Column(String)
    slippage = Column(String, nullable=True)
    net_pnl = Column(String)
    return_pct = Column(String)
    duration_seconds = Column(Float)
    entry_timestamp = Column(TIMESTAMP)
    exit_timestamp = Column(TIMESTAMP)
    metadata_ = Column("metadata", JSON_TYPE, server_default="{}", nullable=True)
