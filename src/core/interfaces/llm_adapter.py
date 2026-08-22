from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, List, Literal, Optional, Type, TypeVar

from pydantic import BaseModel, Field

Structured = TypeVar("Structured", bound=BaseModel)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"] = Field(description="Who authored this turn.")
    content: str = Field(description="The turn's text content.")


class LlmAdapter(ABC):
    @abstractmethod
    def generate(self, prompt: str, history: Optional[List[ChatTurn]] = None) -> str:
        pass

    @abstractmethod
    async def stream(self, prompt: str, history: Optional[List[ChatTurn]] = None) -> AsyncIterator[str]:
        pass

    @abstractmethod
    def bind_tools(self, tools: List[Any]) -> None:
        pass

    @abstractmethod
    def generate_structured(self, schema: Type[Structured], prompt: str, system_prompt: str) -> Structured:
        pass

