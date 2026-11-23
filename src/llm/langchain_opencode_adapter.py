from __future__ import annotations

import uuid
from typing import Optional

from langchain_openai import ChatOpenAI

from src.core.interfaces.llm_adapter import LlmAdapter
from src.llm.base_langchain_adapter import BaseLangChainAdapter

OPENCODE_API_BASE = "https://opencode.ai/inference/go/openai/v1"


class LangChainOpenCodeAdapter(BaseLangChainAdapter, LlmAdapter):
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
        request_timeout = timeout if timeout is not None else 60.0
        extra_kwargs = {"max_tokens": max_tokens} if max_tokens is not None else {}
        resolved_session_id = session_id or str(uuid.uuid4())
        self._model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url or OPENCODE_API_BASE,
            temperature=temperature,
            request_timeout=request_timeout,
            max_retries=max_retries,
            default_headers={
                "x-opencode-session": resolved_session_id,
                "User-Agent": self.USER_AGENT,
            },
            **extra_kwargs,
        )
        self._bound_model = self._model
