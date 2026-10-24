from __future__ import annotations

from typing import Any, AsyncIterator, List, Optional, Type, TypeVar

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from src.core.interfaces.llm_adapter import ChatTurn, LlmAdapter
from src.llm.base_langchain_adapter import BaseLangChainAdapter

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
        try:
            return self._manager.get_active_adapter().generate(
                prompt=prompt, history=history, system_prompt=system_prompt
            )
        except Exception as exc:  # pylint: disable=broad-except
            if self._should_failover(exc):
                fallback = self._try_failover(exc)
                if fallback is not None:
                    return fallback.generate(
                        prompt=prompt, history=history, system_prompt=system_prompt
                    )
            raise

    async def stream(
            self,
            prompt: str,
            history: Optional[List[ChatTurn]] = None,
            system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        try:
            async for chunk in self._manager.get_active_adapter().stream(
                prompt=prompt, history=history, system_prompt=system_prompt
            ):
                yield chunk
        except Exception as exc:  # pylint: disable=broad-except
            if self._should_failover(exc):
                fallback = self._try_failover(exc)
                if fallback is not None:
                    async for chunk in fallback.stream(
                        prompt=prompt, history=history, system_prompt=system_prompt
                    ):
                        yield chunk
                    return
            raise

    def bind_tools(self, tools: List[BaseTool]) -> None:
        self._manager.set_bound_tools(tools)

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._manager.get_active_adapter().get_tool(name)

    def generate_structured(
            self, schema: Type[Structured], prompt: str, system_prompt: str
    ) -> Structured:
        try:
            return self._manager.get_active_adapter().generate_structured(
                schema=schema, prompt=prompt, system_prompt=system_prompt
            )
        except Exception as exc:  # pylint: disable=broad-except
            if self._should_failover(exc):
                fallback = self._try_failover(exc)
                if fallback is not None:
                    return fallback.generate_structured(
                        schema=schema, prompt=prompt, system_prompt=system_prompt
                    )
            raise

    @staticmethod
    def _should_failover(exc: Exception) -> bool:
        return BaseLangChainAdapter.is_non_recoverable_provider_error(exc)

    def _try_failover(self, exc: Exception) -> Optional[LlmAdapter]:
        failover_fn = getattr(self._manager, "try_failover_adapter", None)
        if callable(failover_fn):
            return failover_fn(str(exc))
        return None
