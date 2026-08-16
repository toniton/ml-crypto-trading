from abc import ABC, abstractmethod
from typing import Any, List


class LlmAdapter(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generates a response from the LLM based on the given prompt."""

    @abstractmethod
    def bind_tools(self, tools: List[Any]) -> None:
        """Binds a list of tools to the LLM."""
