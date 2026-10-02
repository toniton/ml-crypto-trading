from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Literal, Optional, Type, TypeVar

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

Structured = TypeVar("Structured", bound=BaseModel)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"] = Field(description="Who authored this turn.")
    content: str = Field(description="The turn's text content.")


class LlmAdapter(ABC):
    @abstractmethod
    def generate(
            self,
            prompt: str,
            history: Optional[List[ChatTurn]] = None,
            system_prompt: Optional[str] = None,
    ) -> str:
        pass

    @abstractmethod
    async def stream(
            self,
            prompt: str,
            history: Optional[List[ChatTurn]] = None,
            system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        pass

    @abstractmethod
    def bind_tools(self, tools: List[BaseTool]) -> None:
        pass

    @abstractmethod
    def get_tool(self, name: str) -> Optional[BaseTool]:
        pass

    @abstractmethod
    def generate_structured(self, schema: Type[Structured], prompt: str, system_prompt: str) -> Structured:
        pass
