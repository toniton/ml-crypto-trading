from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.agent.conversation_manager import ConversationManager
from src.core.interfaces.llm_adapter import ChatTurn
from src.database.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_conversation_repository import PostgresConversationRepository


@pytest.fixture
def mock_db_manager():
    engine = create_engine("sqlite:///:memory:")
    DatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    db_mgr = DatabaseManager()
    db_mgr.engine = engine
    db_mgr._session_factory = session_factory

    return db_mgr


class TestConversationManager:
    def test_round_trip(self, mock_db_manager):
        manager = ConversationManager(mock_db_manager)
        sid = manager.get_or_create(None)
        assert manager.history(sid) == []
        manager.append(sid, ChatTurn(role="user", content="hi"))
        manager.append(sid, ChatTurn(role="assistant", content="hello"))
        assert [turn.content for turn in manager.history(sid)] == ["hi", "hello"]

    def test_resume_existing_session(self, mock_db_manager):
        manager = ConversationManager(mock_db_manager)
        sid = manager.get_or_create(None)
        manager.append(sid, ChatTurn(role="user", content="first"))
        assert manager.get_or_create(sid) == sid
        assert [turn.content for turn in manager.history(sid)] == ["first"]

    def test_memory_window_is_short(self, mock_db_manager):
        manager = ConversationManager(mock_db_manager, memory_max_turns=2)
        sid = manager.get_or_create(None)
        for i in range(5):
            manager.append(sid, ChatTurn(role="user", content=f"m{i}"))
        assert [turn.content for turn in manager.history(sid)] == ["m3", "m4"]

    def test_persisted_history_keeps_more_than_memory(self, mock_db_manager):
        manager = ConversationManager(mock_db_manager, memory_max_turns=2, persisted_max_turns=100)
        sid = manager.get_or_create(None)
        for i in range(5):
            manager.append(sid, ChatTurn(role="user", content=f"m{i}"))
        with mock_db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresConversationRepository)
            persisted = repository.get_history(sid, 1000)
        assert len(persisted) == 5

    def test_persisted_cap_enforced(self, mock_db_manager):
        manager = ConversationManager(mock_db_manager, memory_max_turns=2, persisted_max_turns=3)
        sid = manager.get_or_create(None)
        for i in range(6):
            manager.append(sid, ChatTurn(role="user", content=f"m{i}"))
        with mock_db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresConversationRepository)
            persisted = repository.get_history(sid, 1000)
        assert [turn.content for turn in persisted] == ["m3", "m4", "m5"]

    def test_cache_hydrates_from_db_on_miss(self, mock_db_manager):
        first = ConversationManager(mock_db_manager, memory_max_turns=3)
        sid = first.get_or_create(None)
        first.append(sid, ChatTurn(role="user", content="a"))
        first.append(sid, ChatTurn(role="user", content="b"))

        second = ConversationManager(mock_db_manager, memory_max_turns=3)
        assert [turn.content for turn in second.history(sid)] == ["a", "b"]
