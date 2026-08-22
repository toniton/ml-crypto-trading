from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from src.core.interfaces.llm_adapter import ChatTurn


class ConversationStore(ABC):
    @abstractmethod
    def get_or_create(self, session_id: Optional[str]) -> str:
        raise NotImplementedError()

    @abstractmethod
    def history(self, session_id: str) -> List[ChatTurn]:
        raise NotImplementedError()

    @abstractmethod
    def append(self, session_id: str, turn: ChatTurn) -> None:
        raise NotImplementedError()
