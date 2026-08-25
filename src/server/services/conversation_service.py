from __future__ import annotations

import threading
import uuid
from typing import List, Optional

from src.core.interfaces.conversation_store import ConversationMessage, ConversationStore, SessionSummary
from src.core.interfaces.llm_adapter import ChatTurn
from src.database.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_conversation_repository import PostgresConversationRepository


class ConversationService(ConversationStore):
    DEFAULT_MEMORY_MAX_TURNS = 10
    DEFAULT_PERSISTED_MAX_TURNS = 100

    def __init__(
            self,
            db_manager: DatabaseManager,
            memory_max_turns: int = DEFAULT_MEMORY_MAX_TURNS,
            persisted_max_turns: int = DEFAULT_PERSISTED_MAX_TURNS,
    ):
        self._db_manager = db_manager
        self._memory_max_turns = memory_max_turns
        self._persisted_max_turns = persisted_max_turns
        self._cache: dict[str, List[ChatTurn]] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: Optional[str]) -> str:
        resolved = session_id or uuid.uuid4().hex
        with self._db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresConversationRepository)
            repository.get_or_create(resolved)
        with self._lock:
            self._cache.setdefault(resolved, [])
        return resolved

    def history(self, session_id: str) -> List[ChatTurn]:
        with self._lock:
            if session_id in self._cache:
                return list(self._cache[session_id])
        with self._db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresConversationRepository)
            turns = repository.get_history(session_id, self._memory_max_turns)
        with self._lock:
            self._cache[session_id] = list(turns)
        return list(turns)

    def append(self, session_id: str, message: ConversationMessage) -> None:
        with self._db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresConversationRepository)
            repository.append(session_id, message, self._persisted_max_turns)
        with self._lock:
            turns = self._cache.setdefault(session_id, [])
            turns.append(ChatTurn(role=message.role, content=message.content))
            if len(turns) > self._memory_max_turns:
                del turns[: len(turns) - self._memory_max_turns]

    def messages(self, session_id: str) -> List[ConversationMessage]:
        with self._db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresConversationRepository)
            return repository.get_messages(session_id)

    def get_message(self, message_id: str) -> Optional[ConversationMessage]:
        with self._db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresConversationRepository)
            return repository.get_by_message_id(message_id)

    def list_sessions(self) -> List[SessionSummary]:
        with self._db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresConversationRepository)
            return repository.list_sessions()
