from __future__ import annotations

from typing import Optional

from langchain_google_genai import ChatGoogleGenerativeAI

from src.core.interfaces.llm_adapter import LlmAdapter
from src.llm.base_langchain_adapter import BaseLangChainAdapter


class LangChainGeminiAdapter(BaseLangChainAdapter, LlmAdapter):
    # pylint: disable=too-many-arguments,too-many-positional-arguments
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
            thinking_budget: int | None = 0,
    ):
        super().__init__(max_turns=max_turns, system_prompt=system_prompt)
        request_timeout = timeout if timeout is not None else 60.0
        self._model = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            timeout=request_timeout,
            max_retries=max_retries,
            thinking_budget=thinking_budget,
        )
        self._bound_model = self._model
