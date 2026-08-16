from __future__ import annotations

from langchain_ollama import ChatOllama

from src.core.interfaces.llm_adapter import LlmAdapter
from src.llm.base_langchain_adapter import BaseLangChainAdapter


class LangChainOllamaAdapter(BaseLangChainAdapter, LlmAdapter):
    def __init__(
            self,
            model_name: str,
            base_url: str,
            temperature: float = 0.0,
            timeout: float | None = None,
            keep_alive: str | None = None,
            max_turns: int = 5,
            system_prompt: str | None = None,
    ):
        super().__init__(max_turns=max_turns, system_prompt=system_prompt)
        client_kwargs = {}
        if timeout is not None:
            client_kwargs["timeout"] = timeout
        self._model = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=temperature,
            keep_alive=keep_alive,
            client_kwargs=client_kwargs,
        )
        self._bound_model = self._model
