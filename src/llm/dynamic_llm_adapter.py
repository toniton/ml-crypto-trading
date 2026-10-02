from __future__ import annotations

from typing import Any, AsyncIterator, List, Optional, Type, TypeVar

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from src.core.interfaces.llm_adapter import ChatTurn, LlmAdapter

Structured = TypeVar("Structured", bound=BaseModel)


class DynamicLlmAdapter(LlmAdapter):
    """Proxy adapter that routes calls to the dynamically active LLM instance."""

    def __init__(self, manager: Any):
        self._manager = manager


    def generate(
            self,
            prompt: str,
            history: Optional[List[ChatTurn]] = None,
            system_prompt: Optional[str] = None,
    ) -> str:
        return self._manager.get_active_adapter().generate(
            prompt=prompt, history=history, system_prompt=system_prompt
        )

    async def stream(
            self,
            prompt: str,
            history: Optional[List[ChatTurn]] = None,
            system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        async for chunk in self._manager.get_active_adapter().stream(
            prompt=prompt, history=history, system_prompt=system_prompt
        ):
            yield chunk

    def bind_tools(self, tools: List[BaseTool]) -> None:
        self._manager.set_bound_tools(tools)

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._manager.get_active_adapter().get_tool(name)

    def generate_structured(
            self, schema: Type[Structured], prompt: str, system_prompt: str
    ) -> Structured:
        return self._manager.get_active_adapter().generate_structured(
            schema=schema, prompt=prompt, system_prompt=system_prompt
        )
