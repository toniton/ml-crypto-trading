from __future__ import annotations

import abc
from typing import List

from src.core.interfaces.llm_adapter import ChatTurn
from src.database.repositories.base_repository import BaseRepository


class ConversationRepository(BaseRepository[ChatTurn]):
    @abc.abstractmethod
    def get_or_create(self, session_id: str) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_history(self, session_id: str, limit: int) -> List[ChatTurn]:
        raise NotImplementedError()

    @abc.abstractmethod
    def append(self, session_id: str, turn: ChatTurn, max_turns: int) -> None:
        raise NotImplementedError()
