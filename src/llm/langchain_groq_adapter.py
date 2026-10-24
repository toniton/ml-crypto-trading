from __future__ import annotations

from typing import Optional

from langchain_openai import ChatOpenAI

from src.core.interfaces.llm_adapter import LlmAdapter
from src.llm.base_langchain_adapter import BaseLangChainAdapter

GROQ_API_BASE = "https://api.groq.com/openai/v1"


class LangChainGroqAdapter(BaseLangChainAdapter, LlmAdapter):
    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            model_name: str,
            api_key: str,
            temperature: float = 0.0,
            timeout: float | None = None,
            base_url: Optional[str] = None,
            max_turns: int = 5,
            system_prompt: str | None = None,
            max_retries: int = 2,
            max_tokens: Optional[int] = None,
    ):
        super().__init__(max_turns=max_turns, system_prompt=system_prompt)
        request_timeout = timeout if timeout is not None else 60.0
        resolved_max_tokens = max_tokens
        if resolved_max_tokens is None and "qwen3.8-27b" in model_name.lower():
            resolved_max_tokens = 800
        extra_kwargs = {"max_tokens": resolved_max_tokens} if resolved_max_tokens is not None else {}
        self._model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url or GROQ_API_BASE,
            temperature=temperature,
            request_timeout=request_timeout,
            max_retries=max_retries,
            **extra_kwargs,
        )
        self._bound_model = self._model
