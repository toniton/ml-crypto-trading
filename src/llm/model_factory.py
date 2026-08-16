import os

from dotenv import load_dotenv

from src.configuration.trading_config import LlmProvider, LlmSettings
from src.core.interfaces.llm_adapter import LlmAdapter
from src.llm.langchain_deepseek_adapter import LangChainDeepSeekAdapter
from src.llm.langchain_gemini_adapter import LangChainGeminiAdapter
from src.llm.langchain_groq_adapter import LangChainGroqAdapter
from src.llm.langchain_ollama_adapter import LangChainOllamaAdapter

DEEPSEEK_API_KEY_ENV = "LLM_PROVIDER__DEEPSEEK__API_KEY"
GEMINI_API_KEY_ENV = "LLM_PROVIDER__GEMINI__API_KEY"
GROQ_API_KEY_ENV = "LLM_PROVIDER__GROQ__API_KEY"


class ModelFactory:
    @staticmethod
    def create_model(settings: LlmSettings) -> LlmAdapter:
        if settings.provider == LlmProvider.DEEPSEEK:
            return LangChainDeepSeekAdapter(
                model_name=settings.model,
                api_key=ModelFactory._resolve_api_key(settings, DEEPSEEK_API_KEY_ENV, "DeepSeek"),
                base_url=settings.base_url,
                temperature=settings.temperature,
                timeout=settings.timeout,
            )
        if settings.provider == LlmProvider.GEMINI:
            return LangChainGeminiAdapter(
                model_name=settings.model,
                api_key=ModelFactory._resolve_api_key(settings, GEMINI_API_KEY_ENV, "Gemini"),
                base_url=settings.base_url,
                temperature=settings.temperature,
                timeout=settings.timeout,
            )
        if settings.provider == LlmProvider.GROQ:
            return LangChainGroqAdapter(
                model_name=settings.model,
                api_key=ModelFactory._resolve_api_key(settings, GROQ_API_KEY_ENV, "Groq"),
                base_url=settings.base_url,
                temperature=settings.temperature,
                timeout=settings.timeout,
            )
        return LangChainOllamaAdapter(
            model_name=settings.model,
            base_url=settings.base_url or "http://localhost:11434",
            temperature=settings.temperature,
            timeout=settings.timeout,
            keep_alive=settings.keep_alive,
        )

    @staticmethod
    def _resolve_api_key(settings: LlmSettings, env_var: str, provider_name: str) -> str:
        if settings.api_key:
            return settings.api_key
        load_dotenv()
        api_key = os.environ.get(env_var) or os.environ.get(f"{provider_name.upper()}_API_KEY")
        if not api_key:
            raise ValueError(
                f"No {provider_name} API key configured. Set '{env_var}' in .env "
                "or provide `llm.api_key` in the trading config."
            )
        return api_key
