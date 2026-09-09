from __future__ import annotations

import pytest

from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.unit_of_work import UnitOfWork
from src.database.noop_database_manager import NoopDatabaseManager, NoopRepository, NoopUnitOfWork
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository


class TestNoopDatabaseManager:
    def test_implements_database_manager_interface(self):
        manager = NoopDatabaseManager()
        assert isinstance(manager, DatabaseManager)

    def test_initialize_is_noop(self):
        manager = NoopDatabaseManager()
        manager.initialize()

    def test_get_unit_of_work_returns_noop_uow(self):
        manager = NoopDatabaseManager()
        uow = manager.get_unit_of_work()
        assert isinstance(uow, UnitOfWork)
        assert isinstance(uow, NoopUnitOfWork)


class TestNoopUnitOfWork:
    def test_context_manager_lifecycle(self):
        uow = NoopUnitOfWork()
        with uow as active_uow:
            assert active_uow is uow
            uow.complete()
            uow.rollback()

    def test_context_manager_handles_exception_gracefully(self):
        uow = NoopUnitOfWork()
        with pytest.raises(ValueError, match="test error"):
            with uow:
                raise ValueError("test error")

    def test_get_repository_returns_noop_repository(self):
        uow = NoopUnitOfWork()
        repo = uow.get_repository(PostgresOrderRepository)
        assert isinstance(repo, NoopRepository)


class TestNoopRepository:
    def test_save_returns_entity(self):
        repo = NoopRepository()
        dummy = {"order_id": "123"}
        assert repo.save(dummy) == dummy

    def test_get_returns_none(self):
        repo = NoopRepository()
        assert repo.get("123") is None

    def test_get_all_returns_empty_list(self):
        repo = NoopRepository()
        assert repo.get_all() == []

    def test_update_and_upsert_do_not_raise(self):
        repo = NoopRepository()
        repo.update("123", {"status": "filled"})
        repo.upsert({"status": "filled"})

    def test_query_methods_return_empty_lists(self):
        repo = NoopRepository()
        assert repo.get_non_terminal() == []
        assert repo.get_by_date_range() == []
        assert repo.get_by_status("FILLED") == []

    def test_arbitrary_method_call_returns_none(self):
        repo = NoopRepository()
        assert repo.non_existent_method("arg1", key="val") is None
