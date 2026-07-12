from src.configuration.trading_config import LlmSettings
from src.core.interfaces.llm_adapter import LlmAdapter
from src.llm.langchain_ollama_adapter import LangChainOllamaAdapter


class ModelFactory:
    @staticmethod
    def create_model(settings: LlmSettings) -> LlmAdapter:
        return LangChainOllamaAdapter(
            model_name=settings.model,
            base_url=settings.base_url,
            temperature=settings.temperature,
        )
