from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.trade import Trade
from src.database.dao.trade_dao import TradeDao
from src.database.repositories.mappers.trade_db_vs_entity_mapper import TradeDBVSEntityMapper
from src.database.repositories.providers.postgres_trade_repository import PostgresTradeRepository

EXIT_TIME = datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)
ENTRY_TIME = datetime(2026, 8, 22, 9, 0, 0, tzinfo=timezone.utc)


def build_trade_dao(**overrides) -> TradeDao:
    defaults = {
        "trade_id": "trade-123",
        "ticker_symbol": "BTC_USD",
        "entry_order_uuid": "entry-uuid-1",
        "exit_order_uuid": "exit-uuid-2",
        "entry_price": "60000.0",
        "exit_price": "63000.0",
        "quantity": "0.1",
        "gross_pnl": "300.0",
        "fees": "1.5",
        "slippage": "0.5",
        "net_pnl": "298.5",
        "return_pct": "5.0",
        "duration_seconds": 3600.0,
        "entry_timestamp": ENTRY_TIME,
        "exit_timestamp": EXIT_TIME,
        "metadata_": {
            "commit_hash": "abc1234",
            "winning_strategy": "RsiStrategy",
            "strategy_votes": {"RsiStrategy": "BUY"},
        },
    }
    defaults.update(overrides)
    return TradeDao(**defaults)


def build_trade(**overrides) -> Trade:
    defaults = {
        "trade_id": "trade-123",
        "ticker_symbol": "BTC_USD",
        "entry_order_uuid": "entry-uuid-1",
        "exit_order_uuid": "exit-uuid-2",
        "entry_price": Decimal("60000.0"),
        "exit_price": Decimal("63000.0"),
        "quantity": Decimal("0.1"),
        "gross_pnl": Decimal("300.0"),
        "fees": Decimal("1.5"),
        "slippage": Decimal("0.5"),
        "net_pnl": Decimal("298.5"),
        "return_pct": Decimal("5.0"),
        "duration_seconds": 3600.0,
        "entry_timestamp": ENTRY_TIME.timestamp(),
        "exit_timestamp": EXIT_TIME.timestamp(),
        "commit_hash": "abc1234",
        "winning_strategy": "RsiStrategy",
        "strategy_votes": {"RsiStrategy": "BUY"},
    }
    defaults.update(overrides)
    return Trade(**defaults)


class TestPostgresTradeRepositorySave:
    def test_save_adds_trade_dao_to_session(self):
        session = MagicMock()
        repo = PostgresTradeRepository(database_session=session)
        trade = build_trade()

        repo.save(trade)

        session.add.assert_called_once()


class TestPostgresTradeRepositoryGet:
    def test_get_returns_trade_entity_when_found(self):
        session = MagicMock()
        dao = build_trade_dao()
        query = session.query.return_value
        filtered = query.filter.return_value
        filtered.first.return_value = dao

        repo = PostgresTradeRepository(database_session=session)
        result = repo.get("trade-123")

        assert result.trade_id == "trade-123"

    def test_get_returns_none_when_not_found(self):
        session = MagicMock()
        query = session.query.return_value
        filtered = query.filter.return_value
        filtered.first.return_value = None

        repo = PostgresTradeRepository(database_session=session)
        result = repo.get("non-existent")

        assert result is None


class TestPostgresTradeRepositoryGetAll:
    def test_get_all_returns_all_mapped_trades(self):
        session = MagicMock()
        dao = build_trade_dao()
        query = session.query.return_value
        ordered = query.order_by.return_value
        ordered.all.return_value = [dao]

        repo = PostgresTradeRepository(database_session=session)
        result = repo.get_all()

        assert len(result) == 1


class TestPostgresTradeRepositoryUpsert:
    def test_upsert_executes_statement_with_all_fields(self):
        session = MagicMock()
        repo = PostgresTradeRepository(database_session=session)
        trade = build_trade()

        repo.upsert(trade)

        session.execute.assert_called_once()


class TestPostgresTradeRepositoryGetByTickerSymbol:
    def test_get_by_ticker_symbol_filters_and_returns_trades(self):
        session = MagicMock()
        dao = build_trade_dao(ticker_symbol="BTC_USD")
        query = session.query.return_value
        filtered = query.filter.return_value
        ordered = filtered.order_by.return_value
        ordered.all.return_value = [dao]

        repo = PostgresTradeRepository(database_session=session)
        result = repo.get_by_ticker_symbol("BTC_USD")

        assert result[0].ticker_symbol == "BTC_USD"


class TestPostgresTradeRepositoryGetByExitRange:
    def test_get_by_exit_range_returns_matching_trades(self):
        session = MagicMock()
        dao = build_trade_dao()
        query = session.query.return_value
        filtered1 = query.filter.return_value
        filtered2 = filtered1.filter.return_value
        ordered = filtered2.order_by.return_value
        ordered.all.return_value = [dao]

        repo = PostgresTradeRepository(database_session=session)
        start = datetime(2026, 8, 22, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 8, 23, 0, 0, 0, tzinfo=timezone.utc)
        result = repo.get_by_exit_range("BTC_USD", start, end)

        assert len(result) == 1
 
 
class TestTradeDBVSEntityMapper:
    def test_map_to_db_packages_metadata(self):
        trade = build_trade()
        dao = TradeDBVSEntityMapper.map_to_db(trade)
        assert dao.metadata_ == {
            "commit_hash": "abc1234",
            "winning_strategy": "RsiStrategy",
            "strategy_votes": {"RsiStrategy": "BUY"},
        }

    def test_map_to_entity_extracts_metadata(self):
        dao = build_trade_dao()
        trade = TradeDBVSEntityMapper.map_to_entity(dao)
        assert trade.commit_hash == "abc1234"
        assert trade.winning_strategy == "RsiStrategy"
        assert trade.strategy_votes == {"RsiStrategy": "BUY"}
