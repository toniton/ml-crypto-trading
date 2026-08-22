from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class AIEvent:
    """Application-level event emitted while routing a prompt.

    This is the domain protocol between the agent and the transport layer
    (SSE/WebSocket). LangGraph internals are never exposed beyond `AgentGateway.stream`.

    Every event carries a `response_id` so the stream can be correlated with a proposal,
    retried, logged, or acted upon (e.g. an approval action on a later endpoint).
    """

    type: Literal["node_started", "node_completed", "block", "token", "clarification", "done"]
    response_id: str = field(default="")
    id: str = field(default="")
    agent: str = field(default="")
    payload: Any = field(default=None)

    def to_dict(self) -> dict:
        data: dict = {
            "type": self.type,
            "response_id": self.response_id,
            "payload": self.payload,
        }
        if self.type == "block" and self.id:
            data["id"] = self.id
        if self.agent:
            data["agent"] = self.agent
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=self._json_default)

    @staticmethod
    def _json_default(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return asdict(value)
