from __future__ import annotations

import abc
from typing import List, Optional

from src.core.interfaces.conversation_store import ConversationMessage, SessionSummary
from src.core.interfaces.llm_adapter import ChatTurn
from src.database.repositories.base_repository import BaseRepository


class ConversationRepository(BaseRepository[ConversationMessage]):
    @abc.abstractmethod
    def get_or_create(self, session_id: str) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_history(self, session_id: str, limit: int) -> List[ChatTurn]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_messages(self, session_id: str) -> List[ConversationMessage]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_by_message_id(self, message_id: str) -> Optional[ConversationMessage]:
        raise NotImplementedError()

    @abc.abstractmethod
    def list_sessions(self) -> List[SessionSummary]:
        raise NotImplementedError()

    @abc.abstractmethod
    def append(self, session_id: str, message: ConversationMessage, max_turns: int) -> None:
        raise NotImplementedError()
