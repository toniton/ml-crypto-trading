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
from src.backtest.domain.session import BacktestSession
from src.core.interfaces.execution_status import ExecutionStatus
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
        status=ExecutionStatus.COMPLETED,
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
        assert dao.status == ExecutionStatus.COMPLETED.value
        assert dao.config["data_source"]["path"] == "/data/btc.csv"
        assert dao.config["initial_balance"] == "10000.0"

        mapped_session = BacktestDBVSEntityMapper.dao_to_session(dao)
        assert mapped_session.id == session.id
        assert mapped_session.ticker_symbol == "BTC_USD"
        assert mapped_session.status == ExecutionStatus.COMPLETED
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

    def test_acquire_session_success(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        dao = BacktestSessionDao(
            id="bt_001",
            ticker_symbol="BTC_USD",
            status="QUEUED",
        )
        filtered.first.return_value = dao

        repo = PostgresBacktestRepository(database_session=session_mock)
        acquired = repo.acquire_session("bt_001", worker_id="worker_bt", lease_duration_seconds=60)

        assert acquired is True
        assert dao.status == "RUNNING"
        assert dao.worker_id == "worker_bt"
        assert dao.lease_expires_at is not None
        session_mock.flush.assert_called_once()

    def test_renew_lease_success(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        dao = BacktestSessionDao(
            id="bt_001",
            status="RUNNING",
            worker_id="worker_bt",
        )
        filtered.first.return_value = dao

        repo = PostgresBacktestRepository(database_session=session_mock)
        renewed = repo.renew_lease("bt_001", worker_id="worker_bt", lease_duration_seconds=120)

        assert renewed is True
        assert dao.lease_expires_at is not None
        session_mock.flush.assert_called_once()

    def test_mark_completed_and_failed(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        dao = BacktestSessionDao(id="bt_001", status="RUNNING")
        filtered.first.return_value = dao

        repo = PostgresBacktestRepository(database_session=session_mock)
        res = build_result()
        repo.mark_completed("bt_001", res)
        assert dao.status == "COMPLETED"
        assert dao.lease_expires_at is None

        repo.mark_failed("bt_001", error_message="Engine failure")
        assert dao.status == "FAILED"
        assert dao.error_message == "Engine failure"

    def test_mark_cancelled(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        dao = BacktestSessionDao(id="bt_001", status="QUEUED")
        filtered.first.return_value = dao

        repo = PostgresBacktestRepository(database_session=session_mock)
        cancelled = repo.mark_cancelled("bt_001", reason="User cancel")

        assert cancelled is True
        assert dao.status == "CANCELLED"
        assert dao.error_message == "User cancel"

    def test_recover_abandoned_sessions(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        dao1 = BacktestSessionDao(id="bt_dead_1", status="RUNNING")
        dao2 = BacktestSessionDao(id="bt_dead_2", status="RUNNING")
        filtered.all.return_value = [dao1, dao2]

        repo = PostgresBacktestRepository(database_session=session_mock)
        recovered = repo.recover_abandoned_sessions(timeout_seconds=60)

        assert recovered == ["bt_dead_1", "bt_dead_2"]
        assert dao1.status == "FAILED"
        assert dao2.status == "FAILED"
        assert dao1.error_message is not None

    def test_is_session_active(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        filtered.first.return_value = ("RUNNING",)
        repo = PostgresBacktestRepository(database_session=session_mock)
        assert repo.is_session_active("bt_001") is True

        filtered.first.return_value = ("COMPLETED",)
        assert repo.is_session_active("bt_002") is False

