from __future__ import annotations

from typing import Optional

from langchain_openai import ChatOpenAI

from src.core.interfaces.llm_adapter import LlmAdapter
from src.llm.base_langchain_adapter import BaseLangChainAdapter

GROQ_API_BASE = "https://api.groq.com/openai/v1"


class LangChainGroqAdapter(BaseLangChainAdapter, LlmAdapter):
    def __init__(
            self,
            model_name: str,
            api_key: str,
            temperature: float = 0.0,
            timeout: float | None = None,
            base_url: Optional[str] = None,
            max_turns: int = 5,
            system_prompt: str | None = None,
            max_retries: int = 2,
    ):
        super().__init__(max_turns=max_turns, system_prompt=system_prompt)
        request_timeout = timeout if timeout is not None else 60.0
        self._model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url or GROQ_API_BASE,
            temperature=temperature,
            request_timeout=request_timeout,
            max_retries=max_retries,
        )
        self._bound_model = self._model
