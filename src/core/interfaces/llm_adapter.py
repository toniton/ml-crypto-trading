from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, List, Type, TypeVar

from pydantic import BaseModel

Structured = TypeVar("Structured", bound=BaseModel)


class LlmAdapter(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generates a response from the LLM based on the given prompt."""

    @abstractmethod
    async def stream(self, prompt: str) -> AsyncIterator[str]:
        """Streams response tokens from the LLM based on the given prompt."""

    @abstractmethod
    def bind_tools(self, tools: List[Any]) -> None:
        """Binds a list of tools to the LLM."""

    @abstractmethod
    def generate_structured(self, schema: Type[Structured], prompt: str, system_prompt: str) -> Structured:
        """Generates a response from the LLM that conforms to the given pydantic schema."""
