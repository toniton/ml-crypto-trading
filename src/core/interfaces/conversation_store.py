from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

from src.core.interfaces.llm_adapter import ChatTurn


class ConversationMessage(BaseModel):
    id: Optional[int] = None
    message_id: str = ""
    role: Literal["user", "assistant"]
    content: str
    payload: Optional[dict] = None
    created_at: Optional[datetime] = None


class SessionSummary(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationStore(ABC):
    @abstractmethod
    def get_or_create(self, session_id: Optional[str]) -> str:
        raise NotImplementedError()

    @abstractmethod
    def history(self, session_id: str) -> List[ChatTurn]:
        raise NotImplementedError()

    @abstractmethod
    def append(self, session_id: str, message: ConversationMessage) -> None:
        raise NotImplementedError()

    @abstractmethod
    def messages(self, session_id: str) -> List[ConversationMessage]:
        raise NotImplementedError()

    @abstractmethod
    def list_sessions(self) -> List[SessionSummary]:
        raise NotImplementedError()
