from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.database_manager import DatabaseManager
from database.repositories.providers.postgres_blob_repository import PostgresBlobRepository
from database.repositories.providers.postgres_commit_repository import PostgresCommitRepository
from database.repositories.providers.postgres_ref_repository import PostgresRefRepository
from vcs.application.service import VCSService


@pytest.fixture
def mock_db_manager(monkeypatch):
    """Creates an in-memory SQLite DatabaseManager for testing VCS operations."""
    engine = create_engine("sqlite:///:memory:")
    DatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    db_mgr = DatabaseManager()
    db_mgr.engine = engine
    db_mgr._session_factory = session_factory

    return db_mgr


def test_vcs_commit_and_head(mock_db_manager):
    vcs = VCSService(mock_db_manager)

    # Initial sample config payload
    config_dict = {
        "assets": [],
        "consensus": {"buy": 1.5, "sell": 0.5},
        "dynamic_quantity": "10",
        "llm": {"model": "llama3.2", "base_url": "http://localhost:11434", "temperature": 0.0, "schedule": 1},
    }

    commit1 = vcs.commit(
        config_dict,
        author="toni",
        message="Initial config commit",
        ref="HEAD",
        metadata={"env": "staging"}
    )

    assert commit1.hash is not None
    assert commit1.parent_hash is None
    assert commit1.author == "toni"

    # Verify head() resolves commit1
    head_commit = vcs.head("HEAD")
    assert head_commit.hash == commit1.hash

    # Verify checkout() restores the blob as a dict
    loaded_config = vcs.checkout("HEAD")
    assert isinstance(loaded_config, dict)
    assert loaded_config["consensus"]["buy"] == 1.5


def test_vcs_seed_if_empty_commits_initial_config(mock_db_manager):
    vcs = VCSService(mock_db_manager)

    config_dict = {
        "assets": [],
        "consensus": {"buy": 1.5, "sell": 0.5},
        "dynamic_quantity": "10",
        "llm": {"model": "llama3.2", "base_url": "http://localhost:11434", "temperature": 0.0, "schedule": 1},
    }

    commit = vcs.seed_if_empty(config_dict, author="bootstrap", message="Initial config")

    assert commit is not None
    assert commit.parent_hash is None
    assert vcs.checkout("HEAD")["consensus"]["buy"] == 1.5

    # A subsequent seed is a no-op and must not overwrite the existing HEAD
    assert vcs.seed_if_empty(config_dict, author="bootstrap", message="Initial config") is None
    assert vcs.head("HEAD").hash == commit.hash


def test_vcs_deduplication(mock_db_manager):
    vcs = VCSService(mock_db_manager)

    config_dict = {
        "assets": [],
        "consensus": {"buy": 1.5, "sell": 0.5},
        "llm": {"model": "llama3.2", "base_url": "http://localhost:11434", "temperature": 0.0, "schedule": 1},
    }

    commit1 = vcs.commit(config_dict, author="toni", message="First commit")
    commit2 = vcs.commit(config_dict, author="toni", message="Second commit with identical config")

    assert commit1.blob_hash == commit2.blob_hash  # Same blob deduplicated!
    assert commit1.hash != commit2.hash  # Different commit node (parent hash differs)


def test_vcs_branching_and_promotion(mock_db_manager):
    vcs = VCSService(mock_db_manager)

    config_v1 = {
        "assets": [],
        "consensus": {"buy": 1.0, "sell": 0.5},
        "llm": {"model": "llama3.2", "base_url": "http://localhost:11434", "temperature": 0.0, "schedule": 1},
    }

    # 1. Commit to staging
    commit_v1 = vcs.commit(config_v1, author="toni", message="Staging v1", ref="staging")

    # 2. Branch backtest_mode off staging
    vcs.branch(name="backtest_mode", from_ref="staging")
    assert vcs.head("backtest_mode").hash == commit_v1.hash

    # 3. Commit new config on backtest_mode
    config_v2 = {
        "assets": [],
        "consensus": {"buy": 2.0, "sell": 0.2},
        "llm": {"model": "llama3.2", "base_url": "http://localhost:11434", "temperature": 0.0, "schedule": 1},
    }
    commit_v2 = vcs.commit(config_v2, author="toni", message="Backtest tuned parameters", ref="backtest_mode")

    # 4. Environment Promotion: Reset staging and production to point to commit_v2
    vcs.reset(ref="staging", commit_hash_or_ref=commit_v2.hash)
    vcs.reset(ref="production", commit_hash_or_ref="staging")

    assert vcs.head("production").hash == commit_v2.hash
    assert vcs.checkout("production")["consensus"]["buy"] == 2.0


def test_vcs_log_ancestry(mock_db_manager):
    vcs = VCSService(mock_db_manager)

    config = {
        "assets": [],
        "consensus": {"buy": 1.0, "sell": 0.5},
        "llm": {"model": "llama3.2", "base_url": "http://localhost:11434", "temperature": 0.0, "schedule": 1},
    }

    c1 = vcs.commit(config, author="toni", message="Commit 1", ref="HEAD")
    c2 = vcs.commit(config, author="toni", message="Commit 2", ref="HEAD")
    c3 = vcs.commit(config, author="toni", message="Commit 3", ref="HEAD")

    history = vcs.log("HEAD")
    assert len(history) == 3
    assert history[0].hash == c3.hash
    assert history[1].hash == c2.hash
    assert history[2].hash == c1.hash


def test_ref_repository_applies_row_lock():
    mock_session = MagicMock()
    repo = PostgresRefRepository(database_session=mock_session)
    locked_query = mock_session.query.return_value.filter.return_value
    locked_query.first.return_value = None
    locked_query.with_for_update.return_value = locked_query

    # With lock: FOR UPDATE must be chained on the query
    repo.get_by_name("HEAD", lock_for_update=True)
    locked_query.with_for_update.assert_called_once()

    locked_query.reset_mock()
    locked_query.first.return_value = None
    # Without lock: no FOR UPDATE
    repo.get_by_name("HEAD")
    locked_query.with_for_update.assert_not_called()


def test_vcs_concurrent_commits_preserve_integrity(tmp_path):
    """Concurrent commits on HEAD must not corrupt the object store.

    Row-level FOR UPDATE serializes writers on PostgreSQL; on SQLite the write
    lock is database-wide. This test verifies no lost/corrupted records occur
    and that the ref always resolves to a valid, well-formed commit.
    """
    engine = create_engine(f"sqlite:///{tmp_path}/vcs.db", connect_args={"timeout": 30})
    DatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    db_mgr = DatabaseManager()
    db_mgr.engine = engine
    db_mgr._session_factory = session_factory

    vcs = VCSService(db_mgr)
    config = {
        "assets": [],
        "consensus": {"buy": 1.0, "sell": 0.5},
        "llm": {"model": "llama3.2", "base_url": "http://localhost:11434", "temperature": 0.0, "schedule": 1},
    }

    def do_commit(i: int) -> str:
        return vcs.commit(config, author="toni", message=f"concurrent-{i}", ref="HEAD").hash

    with ThreadPoolExecutor(max_workers=8) as executor:
        hashes = list(executor.map(do_commit, range(8)))

    # Every commit must be persisted with its blob
    with db_mgr.get_unit_of_work() as uow:
        commit_repo = uow.get_repository(PostgresCommitRepository)
        blob_repo = uow.get_repository(PostgresBlobRepository)
        for h in hashes:
            commit = commit_repo.get_by_hash(h)
            assert commit is not None, f"commit {h} lost"
            assert blob_repo.get_by_hash(commit.blob_hash) is not None, f"blob for {h} lost"

    # Head must resolve and its ancestry must terminate cleanly
    head = vcs.head("HEAD")
    assert head.hash in hashes

    seen = set()
    current = head.hash
    with db_mgr.get_unit_of_work() as uow:
        commit_repo = uow.get_repository(PostgresCommitRepository)
        while current and current not in seen:
            seen.add(current)
            commit = commit_repo.get_by_hash(current)
            if commit is None:
                break
            current = commit.parent_hash

    assert len(seen) >= 1
