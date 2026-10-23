from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.database.dao.walk_forward_dao import WalkForwardRunDao
from src.database.repositories.providers.postgres_walk_forward_repository import (
    PostgresWalkForwardRepository,
)


class TestPostgresWalkForwardRepository:
    def test_save_run_and_get(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        dao = WalkForwardRunDao(
            id="wf_001",
            ticker_symbol="BTC_USD",
            status="QUEUED",
            spec={"ticker_symbol": "BTC_USD"},
            summary=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        filtered.first.side_effect = [None, dao]

        repo = PostgresWalkForwardRepository(database_session=session_mock)
        repo.save_run(
            run_id="wf_001",
            ticker_symbol="BTC_USD",
            status="QUEUED",
            spec={"ticker_symbol": "BTC_USD"},
        )

        session_mock.add.assert_called_once()
        session_mock.flush.assert_called_once()

        fetched = repo.get_run("wf_001")
        assert fetched is not None
        assert fetched["run_id"] == "wf_001"
        assert fetched["status"] == "QUEUED"

    def test_acquire_run_success(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        dao = WalkForwardRunDao(
            id="wf_001",
            ticker_symbol="BTC_USD",
            status="QUEUED",
        )
        filtered.first.return_value = dao

        repo = PostgresWalkForwardRepository(database_session=session_mock)
        acquired = repo.acquire_run("wf_001", worker_id="worker_1", lease_duration_seconds=60)

        assert acquired is True
        assert dao.status == "RUNNING"
        assert dao.worker_id == "worker_1"
        assert dao.lease_expires_at is not None
        session_mock.flush.assert_called_once()

    def test_acquire_run_missing_or_not_queued(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value
        filtered.first.return_value = None

        repo = PostgresWalkForwardRepository(database_session=session_mock)
        acquired = repo.acquire_run("wf_missing", worker_id="worker_1", lease_duration_seconds=60)

        assert acquired is False

    def test_renew_lease_success(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        dao = WalkForwardRunDao(
            id="wf_001",
            status="RUNNING",
            worker_id="worker_1",
        )
        filtered.first.return_value = dao

        repo = PostgresWalkForwardRepository(database_session=session_mock)
        renewed = repo.renew_lease("wf_001", worker_id="worker_1", lease_duration_seconds=120)

        assert renewed is True
        assert dao.lease_expires_at is not None
        session_mock.flush.assert_called_once()

    def test_mark_completed(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        dao = WalkForwardRunDao(
            id="wf_001",
            status="RUNNING",
        )
        filtered.first.return_value = dao

        repo = PostgresWalkForwardRepository(database_session=session_mock)
        repo.mark_completed("wf_001", summary={"verdict": "ROBUST"})

        assert dao.status == "COMPLETED"
        assert dao.summary == {"verdict": "ROBUST"}
        assert dao.completed_at is not None
        assert dao.lease_expires_at is None
        session_mock.flush.assert_called_once()

    def test_mark_failed(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        dao = WalkForwardRunDao(
            id="wf_001",
            status="RUNNING",
        )
        filtered.first.return_value = dao

        repo = PostgresWalkForwardRepository(database_session=session_mock)
        repo.mark_failed("wf_001", error_message="Fatal crash")

        assert dao.status == "FAILED"
        assert dao.error_message == "Fatal crash"
        assert dao.completed_at is not None
        assert dao.lease_expires_at is None
        session_mock.flush.assert_called_once()

    def test_mark_cancelled(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        dao = WalkForwardRunDao(
            id="wf_001",
            status="QUEUED",
        )
        filtered.first.return_value = dao

        repo = PostgresWalkForwardRepository(database_session=session_mock)
        cancelled = repo.mark_cancelled("wf_001", reason="User cancelled")

        assert cancelled is True
        assert dao.status == "CANCELLED"
        assert dao.error_message == "User cancelled"
        assert dao.lease_expires_at is None
        session_mock.flush.assert_called_once()

    def test_recover_abandoned_runs(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        dao1 = WalkForwardRunDao(id="wf_dead_1", status="RUNNING")
        dao2 = WalkForwardRunDao(id="wf_dead_2", status="RUNNING")
        filtered.all.return_value = [dao1, dao2]

        repo = PostgresWalkForwardRepository(database_session=session_mock)
        recovered = repo.recover_abandoned_runs(timeout_seconds=60)

        assert recovered == ["wf_dead_1", "wf_dead_2"]
        assert dao1.status == "FAILED"
        assert dao2.status == "FAILED"
        assert dao1.error_message is not None
        assert dao1.lease_expires_at is None
        session_mock.flush.assert_called_once()

    def test_is_run_active(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered = query.filter.return_value

        filtered.first.return_value = ("RUNNING",)
        repo = PostgresWalkForwardRepository(database_session=session_mock)
        assert repo.is_run_active("wf_001") is True

        filtered.first.return_value = ("COMPLETED",)
        assert repo.is_run_active("wf_002") is False

        filtered.first.return_value = None
        assert repo.is_run_active("wf_missing") is False
