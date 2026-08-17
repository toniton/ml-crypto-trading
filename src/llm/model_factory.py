import os
from typing import Optional

from dotenv import load_dotenv

from src.configuration.llm_config import LlmConfig, LlmModelConfig, LlmProvider
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
    def create_model(config: LlmConfig, model_name: Optional[str] = None) -> LlmAdapter:
        model = config.get_model(model_name) if model_name else config.default_model
        if model.provider == LlmProvider.DEEPSEEK:
            return LangChainDeepSeekAdapter(
                model_name=model.model_name,
                api_key=ModelFactory._resolve_api_key(model, DEEPSEEK_API_KEY_ENV, "DeepSeek"),
                base_url=model.api_base_url,
                temperature=model.temperature,
                timeout=model.timeout,
            )
        if model.provider == LlmProvider.GEMINI:
            return LangChainGeminiAdapter(
                model_name=model.model_name,
                api_key=ModelFactory._resolve_api_key(model, GEMINI_API_KEY_ENV, "Gemini"),
                base_url=model.api_base_url,
                temperature=model.temperature,
                timeout=model.timeout,
            )
        if model.provider == LlmProvider.GROQ:
            return LangChainGroqAdapter(
                model_name=model.model_name,
                api_key=ModelFactory._resolve_api_key(model, GROQ_API_KEY_ENV, "Groq"),
                base_url=model.api_base_url,
                temperature=model.temperature,
                timeout=model.timeout,
            )
        return LangChainOllamaAdapter(
            model_name=model.model_name,
            base_url=model.api_base_url or "http://localhost:11434",
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
        if not api_key:
            raise ValueError(
                f"No {provider_name} API key configured. Set '{env_var}' in .env "
                f"or set `api_key_env` for model '{model.name}' in src/configuration/llm.yaml."
            )
        return api_key