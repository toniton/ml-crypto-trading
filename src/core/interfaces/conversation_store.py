from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

from src.core.interfaces.llm_adapter import ChatTurn


RESERVED_AGENT_SESSION_ID = "agent:system"
RESERVED_AGENT_SESSION_TITLE = "Agent Feed"


class ReservedSessionDeletionError(ValueError):
    """Raised when an attempt is made to delete a reserved system session."""


class ConversationMessage(BaseModel):
    id: Optional[int] = None
    message_id: str = ""
    role: Literal["user", "assistant"]
    content: str
    payload: Optional[dict] = None
    created_at: Optional[datetime] = None
    conversation_id: Optional[str] = None


class SessionSummary(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    title: Optional[str] = None
    is_reserved: bool = False
    session_kind: Literal["user", "agent"] = "user"


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
    def get_message(self, message_id: str) -> Optional[ConversationMessage]:
        raise NotImplementedError()

    @abstractmethod
    def list_sessions(self) -> List[SessionSummary]:
        raise NotImplementedError()
