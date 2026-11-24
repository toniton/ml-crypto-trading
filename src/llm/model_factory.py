from __future__ import annotations

import os
from typing import Callable, Optional

from dotenv import load_dotenv

from src.configuration.llm_config import LlmConfig, LlmModelConfig, LlmProvider
from src.core.interfaces.llm_adapter import LlmAdapter
from src.llm.langchain_deepseek_adapter import LangChainDeepSeekAdapter
from src.llm.langchain_gemini_adapter import LangChainGeminiAdapter
from src.llm.langchain_groq_adapter import LangChainGroqAdapter
from src.llm.langchain_ollama_adapter import LangChainOllamaAdapter
from src.llm.langchain_opencode_adapter import LangChainOpenCodeAdapter

ProviderBuilder = Callable[[LlmModelConfig, Optional[str], Optional[str]], LlmAdapter]

DEEPSEEK_API_KEY_ENV = "LLM_PROVIDER__DEEPSEEK__API_KEY"
GEMINI_API_KEY_ENV = "LLM_PROVIDER__GEMINI__API_KEY"
GROQ_API_KEY_ENV = "LLM_PROVIDER__GROQ__API_KEY"
OPENCODE_API_KEY_ENV = "LLM_PROVIDER__OPENCODE__API_KEY"


class ModelFactory:
    DEEPSEEK_API_KEY_ENV: str = "LLM_PROVIDER__DEEPSEEK__API_KEY"
    GEMINI_API_KEY_ENV: str = "LLM_PROVIDER__GEMINI__API_KEY"
    GROQ_API_KEY_ENV: str = "LLM_PROVIDER__GROQ__API_KEY"
    OPENCODE_API_KEY_ENV: str = "LLM_PROVIDER__OPENCODE__API_KEY"
    OLLAMA_DEFAULT_BASE_URL: str = "http://localhost:11434"

    @classmethod
    def create_model(
            cls,
            config: LlmConfig,
            model_name: Optional[str] = None,
            api_key: Optional[str] = None,
            api_base_url: Optional[str] = None,
    ) -> LlmAdapter:
        model = config.get_model(model_name) if model_name else config.default_model
        resolved_base_url = api_base_url or model.api_base_url
        builder = cls._provider_builders().get(model.provider, cls._create_ollama)
        return builder(model, api_key, resolved_base_url)

    @classmethod
    def _provider_builders(cls) -> dict[LlmProvider, ProviderBuilder]:
        return {
            LlmProvider.DEEPSEEK: cls._create_deepseek,
            LlmProvider.GEMINI: cls._create_gemini,
            LlmProvider.GROQ: cls._create_groq,
            LlmProvider.OPENCODE: cls._create_opencode,
            LlmProvider.OLLAMA: cls._create_ollama,
        }

    @classmethod
    def _create_deepseek(
            cls, model: LlmModelConfig, api_key: Optional[str], base_url: Optional[str]
    ) -> LlmAdapter:
        key = api_key or cls._resolve_api_key(model, cls.DEEPSEEK_API_KEY_ENV, "DeepSeek")
        return LangChainDeepSeekAdapter(
            model_name=model.model_name,
            api_key=key,
            base_url=base_url,
            temperature=model.temperature,
            timeout=model.timeout,
        )

    @classmethod
    def _create_gemini(
            cls, model: LlmModelConfig, api_key: Optional[str], base_url: Optional[str]
    ) -> LlmAdapter:
        key = api_key or cls._resolve_api_key(model, cls.GEMINI_API_KEY_ENV, "Gemini")
        return LangChainGeminiAdapter(
            model_name=model.model_name,
            api_key=key,
            base_url=base_url,
            temperature=model.temperature,
            timeout=model.timeout,
            max_tokens=model.max_tokens,
        )

    @classmethod
    def _create_groq(
            cls, model: LlmModelConfig, api_key: Optional[str], base_url: Optional[str]
    ) -> LlmAdapter:
        key = api_key or cls._resolve_api_key(model, cls.GROQ_API_KEY_ENV, "Groq")
        return LangChainGroqAdapter(
            model_name=model.model_name,
            api_key=key,
            base_url=base_url,
            temperature=model.temperature,
            timeout=model.timeout,
            max_tokens=model.max_tokens,
        )

    @classmethod
    def _create_opencode(
            cls, model: LlmModelConfig, api_key: Optional[str], base_url: Optional[str]
    ) -> LlmAdapter:
        key = api_key or cls._resolve_api_key(model, cls.OPENCODE_API_KEY_ENV, "OpenCode")
        return LangChainOpenCodeAdapter(
            model_name=model.model_name,
            api_key=key,
            base_url=base_url,
            temperature=model.temperature,
            timeout=model.timeout,
            max_tokens=model.max_tokens,
        )

    @classmethod
    def _create_ollama(
            cls, model: LlmModelConfig, _api_key: Optional[str], base_url: Optional[str]
    ) -> LlmAdapter:
        return LangChainOllamaAdapter(
            model_name=model.model_name,
            base_url=base_url or cls.OLLAMA_DEFAULT_BASE_URL,
            temperature=model.temperature,
            timeout=model.timeout,
            keep_alive=model.keep_alive,
        )

    @staticmethod
    def _resolve_api_key(model: LlmModelConfig, env_var: str, provider_name: str) -> str:
        load_dotenv()
        if model.api_key_env:
            api_key = os.environ.get(model.api_key_env)
        else:
            api_key = os.environ.get(env_var) or os.environ.get(f"{provider_name.upper()}_API_KEY")

        if api_key:
            return api_key

        raise ValueError(
            f"No {provider_name} API key configured. Set '{env_var}' in .env, configure in Settings, "
            f"or set `api_key_env` for model '{model.name}' in src/configuration/llm.yaml."
        )
