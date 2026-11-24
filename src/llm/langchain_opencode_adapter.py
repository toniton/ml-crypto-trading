from __future__ import annotations

import uuid
from typing import Optional

from langchain_openai import ChatOpenAI

from src.core.interfaces.llm_adapter import LlmAdapter
from src.llm.base_langchain_adapter import BaseLangChainAdapter


class LangChainOpenCodeAdapter(BaseLangChainAdapter, LlmAdapter):
    DEFAULT_API_BASE: str = "https://opencode.ai/inference/go/openai/v1"
    SESSION_HEADER: str = "x-opencode-session"

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
            session_id: Optional[str] = None,
    ):
        super().__init__(max_turns=max_turns, system_prompt=system_prompt)
        client_kwargs = {
            "model": model_name,
            "api_key": api_key,
            "base_url": base_url or self.DEFAULT_API_BASE,
            "temperature": temperature,
            "request_timeout": self.DEFAULT_TIMEOUT if timeout is None else timeout,
            "max_retries": max_retries,
            "default_headers": self._build_headers(session_id),
        }
        if max_tokens:
            client_kwargs["max_tokens"] = max_tokens
        self._model = ChatOpenAI(**client_kwargs)
        self._bound_model = self._model

    def _build_headers(self, session_id: Optional[str]) -> dict[str, str]:
        return {
            self.SESSION_HEADER: session_id or str(uuid.uuid4()),
            self.USER_AGENT_HEADER: self.USER_AGENT,
        }
