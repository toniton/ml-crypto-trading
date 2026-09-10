from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
    ExecutionConfiguration,
)
from src.backtest.domain.result import BacktestResult
from src.backtest.domain.session import BacktestSession, BacktestSessionStatus
from src.database.dao.backtest_result_dao import BacktestResultDao
from src.database.dao.backtest_session_dao import BacktestSessionDao
from src.database.repositories.mappers.backtest_db_vs_entity_mapper import BacktestDBVSEntityMapper
from src.database.repositories.providers.postgres_backtest_repository import PostgresBacktestRepository


def build_session() -> BacktestSession:
    request = BacktestRequest(
        ticker_symbol="BTC_USD",
        start_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 7, 0, 0, 0, tzinfo=timezone.utc),
        data_source=BacktestDataSourceRequest(
            source_type=BacktestDataSourceType.CSV,
            path="/data/btc.csv",
        ),
        initial_balance=Decimal("10000.0"),
        execution=ExecutionConfiguration(
            latency_ms=500.0,
            slippage_ticks=2,
            fee_rate=Decimal("0.001"),
        ),
    )
    session = BacktestSession(
        id="bt_test_session_123",
        ticker_symbol="BTC_USD",
        request=request,
        status=BacktestSessionStatus.COMPLETED,
    )
    return session


def build_result() -> BacktestResult:
    return BacktestResult(
        session_id="bt_test_session_123",
        ticker_symbol="BTC_USD",
        initial_balance=Decimal("10000.0"),
        final_balance=Decimal("10500.0"),
        final_equity=Decimal("10750.0"),
        execution=ExecutionConfiguration(
            latency_ms=500.0,
            slippage_ticks=2,
            fee_rate=Decimal("0.001"),
        ),
    )


class TestBacktestDBVSEntityMapper:
    def test_session_to_dao_and_back(self):
        session = build_session()
        dao = BacktestDBVSEntityMapper.session_to_dao(session)

        assert dao.id == session.id
        assert dao.ticker_symbol == "BTC_USD"
        assert dao.status == BacktestSessionStatus.COMPLETED.value
        assert dao.config["data_source"]["path"] == "/data/btc.csv"
        assert dao.config["initial_balance"] == "10000.0"

        mapped_session = BacktestDBVSEntityMapper.dao_to_session(dao)
        assert mapped_session.id == session.id
        assert mapped_session.ticker_symbol == "BTC_USD"
        assert mapped_session.status == BacktestSessionStatus.COMPLETED
        assert mapped_session.request.data_source.path == "/data/btc.csv"

    def test_result_to_dao_and_back(self):
        result = build_result()
        metrics = {"percentage_return": "7.5", "max_drawdown_pct": "2.1"}
        dao = BacktestDBVSEntityMapper.result_to_dao(result, metrics=metrics)

        assert dao.session_id == "bt_test_session_123"
        assert dao.ticker_symbol == "BTC_USD"
        assert dao.data["final_equity"] == "10750.0"
        assert dao.data["metrics"]["percentage_return"] == "7.5"

        mapped_result = BacktestDBVSEntityMapper.dao_to_result(dao)
        assert mapped_result.session_id == result.session_id
        assert mapped_result.final_equity == Decimal("10750.0")


class TestPostgresBacktestRepository:
    def test_save_and_get_session(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered_query = query.filter.return_value

        dao = BacktestSessionDao(
            id="bt_123",
            ticker_symbol="BTC_USD",
            status="COMPLETED",
            config={
                "start_time": None,
                "end_time": None,
                "initial_balance": "10000.0",
                "data_source": {"source_type": "csv", "path": "/data"},
            },
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        filtered_query.first.return_value = dao

        repo = PostgresBacktestRepository(database_session=session_mock)
        session = build_session()
        repo.save_session(session)

        session_mock.execute.assert_called_once()
        retrieved = repo.get_session("bt_123")
        assert retrieved is not None
        assert retrieved.id == "bt_123"
        assert retrieved.ticker_symbol == "BTC_USD"

    def test_list_sessions(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        ordered_query = query.order_by.return_value
        limited_query = ordered_query.limit.return_value

        dao = BacktestSessionDao(
            id="bt_123",
            ticker_symbol="BTC_USD",
            status="COMPLETED",
            config={
                "start_time": None,
                "end_time": None,
                "initial_balance": "10000.0",
                "data_source": {"source_type": "csv", "path": "/data"},
            },
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        limited_query.all.return_value = [dao]

        repo = PostgresBacktestRepository(database_session=session_mock)
        sessions = repo.list_sessions(limit=10)
        assert len(sessions) == 1
        assert sessions[0].id == "bt_123"

    def test_save_and_get_result(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered_query = query.filter.return_value

        dao = BacktestResultDao(
            id=1,
            session_id="bt_123",
            ticker_symbol="BTC_USD",
            data={
                "initial_balance": "10000.0",
                "final_balance": "10500.0",
                "final_equity": "10750.0",
                "total_orders": 5,
                "total_fills": 4,
                "execution": {"latency_ms": 500.0, "slippage_ticks": 2, "fee_rate": "0.001"},
                "metrics": {"return_pct": "7.5"},
            },
            created_at=datetime.now(timezone.utc),
        )
        filtered_query.first.return_value = dao

        repo = PostgresBacktestRepository(database_session=session_mock)
        res = build_result()
        repo.save_result(res, metrics={"return_pct": "7.5"})

        session_mock.execute.assert_called_once()
        retrieved = repo.get_result("bt_123")
        assert retrieved is not None
        assert retrieved.session_id == "bt_123"
        assert retrieved.final_equity == Decimal("10750.0")

        metrics = repo.get_result_metrics("bt_123")
        assert metrics == {"return_pct": "7.5"}
