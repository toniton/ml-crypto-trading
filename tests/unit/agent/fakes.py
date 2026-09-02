from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, List, Optional, Type

from src.core.interfaces.conversation_store import ConversationMessage, ConversationStore, SessionSummary
from src.core.interfaces.llm_adapter import ChatTurn, LlmAdapter
from src.agent.router.models import AgentIntent, AgentRoute


class FakeLlmAdapter(LlmAdapter):
    """Scripted LLM adapter used to drive agent graph tests deterministically."""

    def __init__(
            self,
            structured_results: Optional[list] = None,
            text: str = "ok",
            chunks: Optional[list] = None,
            tools: Optional[list] = None,
    ):
        self.structured_results = list(structured_results or [])
        self.structured_calls: List[tuple] = []
        self.text = text
        self.chunks = chunks if chunks is not None else [text]
        self.last_history: Optional[list] = None
        self._tools: dict[str, Any] = {}
        if tools:
            self.bind_tools(tools)

    def generate(self, prompt: str, history: Optional[list] = None) -> str:
        self.last_history = history
        return self.text

    async def stream(self, prompt: str, history: Optional[list] = None) -> AsyncIterator[str]:
        self.last_history = history
        for chunk in self.chunks:
            yield chunk

    def bind_tools(self, tools) -> None:
        self._tools = {
            (getattr(tool, "name", None) or str(tool)).lower(): tool
            for tool in tools
        }

    def get_tool(self, name: str) -> Optional[Any]:
        return self._tools.get(name.lower())


    def generate_structured(self, schema: Type, prompt: str, system_prompt: str):
        self.structured_calls.append((schema, prompt, system_prompt))
        if self.structured_results:
            return self.structured_results.pop(0)
        if schema is AgentRoute:
            return AgentRoute(intent=AgentIntent.GENERAL)
        return schema.model_construct()


class FakeConversationStore(ConversationStore):
    """In-memory ConversationStore fake used by transport-layer tests."""

    def __init__(self, max_turns: int = 10):
        self._sessions: dict[str, List[ConversationMessage]] = {}
        self._max_turns = max_turns

    def get_or_create(self, session_id: Optional[str] = None) -> str:
        resolved = session_id or uuid.uuid4().hex
        self._sessions.setdefault(resolved, [])
        return resolved

    def history(self, session_id: str) -> List[ChatTurn]:
        return [
            ChatTurn(role=message.role, content=message.content)
            for message in self._sessions.get(session_id, [])[-self._max_turns:]
        ]

    def append(self, session_id: str, message: ConversationMessage) -> None:
        message.conversation_id = session_id
        messages = self._sessions.setdefault(session_id, [])
        messages.append(message)
        if len(messages) > self._max_turns:
            del messages[: len(messages) - self._max_turns]

    def messages(self, session_id: str) -> List[ConversationMessage]:
        return list(self._sessions.get(session_id, []))

    def get_message(self, message_id: str) -> Optional[ConversationMessage]:
        for messages in self._sessions.values():
            for message in reversed(messages):
                if message.message_id == message_id and message.role == "assistant":
                    return message
        return None

    def list_sessions(self) -> List[SessionSummary]:
        now = datetime.now(timezone.utc)
        return [
            SessionSummary(id=sid, created_at=now, updated_at=now, message_count=len(messages))
            for sid, messages in self._sessions.items()
        ]
