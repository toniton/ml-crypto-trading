import unittest
from unittest.mock import patch

from src.configuration.trading_config import LlmProvider, LlmSettings
from src.llm.langchain_deepseek_adapter import LangChainDeepSeekAdapter
from src.llm import LangChainGeminiAdapter
from src.llm import LangChainGroqAdapter
from src.llm import LangChainOllamaAdapter
from src.llm import ModelFactory


class TestModelFactory(unittest.TestCase):
    def test_create_model_defaults_to_ollama(self):
        settings = LlmSettings(model="test-model", base_url="http://test")
        model = ModelFactory.create_model(settings)
        self.assertIsInstance(model, LangChainOllamaAdapter)

    def test_create_ollama_model_with_default_base_url(self):
        settings = LlmSettings(model="test-model")
        with patch.object(LangChainOllamaAdapter, "__init__", return_value=None) as mock_init:
            ModelFactory.create_model(settings)
        mock_init.assert_called_once()
        _, kwargs = mock_init.call_args
        self.assertEqual(kwargs["base_url"], "http://localhost:11434")

    @patch("src.llm.model_factory.ModelFactory._resolve_api_key", return_value="sk-test")
    def test_create_deepseek_model(self, _mock_key):
        settings = LlmSettings(
            provider=LlmProvider.DEEPSEEK,
            model="deepseek-chat",
            temperature=0.0,
            timeout=120,
        )
        model = ModelFactory.create_model(settings)
        self.assertIsInstance(model, LangChainDeepSeekAdapter)

    @patch("src.llm.model_factory.ModelFactory._resolve_api_key", return_value="ai-test")
    def test_create_gemini_model(self, _mock_key):
        settings = LlmSettings(
            provider=LlmProvider.GEMINI,
            model="gemini-3-flash-preview",
            temperature=0.0,
            timeout=120,
        )
        model = ModelFactory.create_model(settings)
        self.assertIsInstance(model, LangChainGeminiAdapter)

    @patch("src.llm.model_factory.ModelFactory._resolve_api_key", return_value="gsk-test")
    def test_create_groq_model(self, _mock_key):
        settings = LlmSettings(
            provider=LlmProvider.GROQ,
            model="llama-3.3-70b-versatile",
            temperature=0.0,
            timeout=120,
        )
        model = ModelFactory.create_model(settings)
        self.assertIsInstance(model, LangChainGroqAdapter)

    def test_resolve_deepseek_api_key_from_settings(self):
        settings = LlmSettings(
            provider=LlmProvider.DEEPSEEK,
            api_key="sk-from-settings",
        )
        self.assertEqual(
            ModelFactory._resolve_api_key(settings, "LLM_PROVIDER__DEEPSEEK__API_KEY", "DeepSeek"),
            "sk-from-settings",
        )

    @patch.dict("os.environ", {"LLM_PROVIDER__DEEPSEEK__API_KEY": "sk-from-env"}, clear=False)
    @patch("src.llm.model_factory.load_dotenv")
    def test_resolve_deepseek_api_key_from_env(self, mock_load_dotenv):
        settings = LlmSettings(provider=LlmProvider.DEEPSEEK)
        self.assertEqual(
            ModelFactory._resolve_api_key(settings, "LLM_PROVIDER__DEEPSEEK__API_KEY", "DeepSeek"),
            "sk-from-env",
        )
        mock_load_dotenv.assert_called_once()

    @patch.dict("os.environ", {}, clear=True)
    @patch("src.llm.model_factory.load_dotenv")
    def test_resolve_api_key_missing_raises(self, _mock_load_dotenv):
        settings = LlmSettings(provider=LlmProvider.DEEPSEEK)
        with self.assertRaises(ValueError):
            ModelFactory._resolve_api_key(settings, "LLM_PROVIDER__DEEPSEEK__API_KEY", "DeepSeek")


if __name__ == "__main__":
    unittest.main()