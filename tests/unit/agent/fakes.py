from __future__ import annotations

from typing import AsyncIterator, List, Optional, Type

from src.core.interfaces.llm_adapter import LlmAdapter
from src.agent.router.models import AgentIntent, AgentRoute


class FakeLlmAdapter(LlmAdapter):
    """Scripted LLM adapter used to drive agent graph tests deterministically."""

    def __init__(
            self,
            structured_results: Optional[list] = None,
            text: str = "ok",
            chunks: Optional[list] = None,
    ):
        self.structured_results = list(structured_results or [])
        self.structured_calls: List[tuple] = []
        self.text = text
        self.chunks = chunks if chunks is not None else [text]

    def generate(self, prompt: str) -> str:
        return self.text

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        for chunk in self.chunks:
            yield chunk

    def bind_tools(self, tools) -> None:
        pass

    def generate_structured(self, schema: Type, prompt: str, system_prompt: str):
        self.structured_calls.append((schema, prompt, system_prompt))
        if self.structured_results:
            return self.structured_results.pop(0)
        if schema is AgentRoute:
            return AgentRoute(intent=AgentIntent.GENERAL)
        return schema.model_construct()
