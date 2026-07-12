import unittest

from src.configuration.trading_config import LlmSettings
from src.llm.langchain_ollama_adapter import LangChainOllamaAdapter
from src.llm.model_factory import ModelFactory


class TestModelFactory(unittest.TestCase):
    def test_create_model(self):
        settings = LlmSettings(model="test-model", base_url="http://test")
        model = ModelFactory.create_model(settings)
        self.assertIsInstance(model, LangChainOllamaAdapter)
