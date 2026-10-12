from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.database.dao.experiment_dao import ExperimentDao
from src.database.repositories.providers.postgres_experiment_repository import (
    PostgresExperimentRepository,
)


class TestPostgresExperimentRepository:
    def test_save_experiment_new_and_get(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered_query = query.filter.return_value

        dao = ExperimentDao(
            id="exp_001",
            name="Test Experiment",
            ticker_symbol="BTC_USD",
            branch_id="exp-bt-123",
            base_commit_hash="commit_hash_123",
            status="DRAFT",
            spec={"name": "Test Experiment", "ticker_symbol": "BTC_USD"},
            run_bindings=[],
            report=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        filtered_query.first.side_effect = [None, dao]

        repo = PostgresExperimentRepository(database_session=session_mock)
        repo.save_experiment(
            experiment_id="exp_001",
            name="Test Experiment",
            ticker_symbol="BTC_USD",
            branch_id="exp-bt-123",
            base_commit_hash="commit_hash_123",
            status="DRAFT",
            spec={"name": "Test Experiment", "ticker_symbol": "BTC_USD"},
            run_bindings=[],
            report=None,
        )

        session_mock.add.assert_called_once()
        session_mock.flush.assert_called_once()

        fetched = repo.get_experiment("exp_001")
        assert fetched is not None
        assert fetched["experiment_id"] == "exp_001"
        assert fetched["name"] == "Test Experiment"
        assert fetched["status"] == "DRAFT"

    def test_update_status_and_report(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered_query = query.filter.return_value

        dao = ExperimentDao(
            id="exp_002",
            name="Test Update",
            ticker_symbol="ETH_USD",
            branch_id="exp-eth-123",
            base_commit_hash="commit_hash_456",
            status="DRAFT",
            spec={},
            run_bindings=[],
            report=None,
        )
        filtered_query.first.return_value = dao

        repo = PostgresExperimentRepository(database_session=session_mock)
        repo.update_status("exp_002", "RUNNING")
        assert dao.status == "RUNNING"

        repo.update_report("exp_002", "COMPLETED", {"metrics": {"return_pct": 12.5}})
        assert dao.status == "COMPLETED"
        assert dao.report == {"metrics": {"return_pct": 12.5}}

    def test_delete_experiment(self):
        session_mock = MagicMock()
        query = session_mock.query.return_value
        filtered_query = query.filter.return_value

        dao = ExperimentDao(
            id="exp_003",
            name="To Delete",
            ticker_symbol="BTC_USD",
            branch_id="exp-del-123",
            base_commit_hash="commit_hash_789",
            status="DRAFT",
            spec={},
            run_bindings=[],
            report=None,
        )
        filtered_query.first.return_value = dao

        repo = PostgresExperimentRepository(database_session=session_mock)
        success = repo.delete_experiment("exp_003")

        assert success is True
        session_mock.delete.assert_called_once_with(dao)
        session_mock.flush.assert_called_once()
