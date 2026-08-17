import unittest
from unittest.mock import patch

from src.configuration.llm_config import LlmConfig, LlmModelConfig, LlmProvider
from src.llm.langchain_deepseek_adapter import LangChainDeepSeekAdapter
from src.llm import LangChainGeminiAdapter
from src.llm import LangChainGroqAdapter
from src.llm import LangChainOllamaAdapter
from src.llm import ModelFactory


def _config(*models):
    return LlmConfig.model_construct(models=list(models))


class TestModelFactory(unittest.TestCase):
    def test_create_model_defaults_to_ollama(self):
        config = _config(LlmModelConfig(name="default", provider=LlmProvider.OLLAMA, model_name="test-model"))
        model = ModelFactory.create_model(config)
        self.assertIsInstance(model, LangChainOllamaAdapter)

    def test_create_ollama_model_with_default_base_url(self):
        config = _config(LlmModelConfig(name="default", provider=LlmProvider.OLLAMA, model_name="test-model"))
        with patch.object(LangChainOllamaAdapter, "__init__", return_value=None) as mock_init:
            ModelFactory.create_model(config)
        mock_init.assert_called_once()
        _, kwargs = mock_init.call_args
        self.assertEqual(kwargs["base_url"], "http://localhost:11434")

    @patch("src.llm.model_factory.ModelFactory._resolve_api_key", return_value="sk-test")
    def test_create_deepseek_model(self, _mock_key):
        config = _config(LlmModelConfig(
            name="default", provider=LlmProvider.DEEPSEEK, model_name="deepseek-chat", timeout=120,
        ))
        model = ModelFactory.create_model(config)
        self.assertIsInstance(model, LangChainDeepSeekAdapter)

    @patch("src.llm.model_factory.ModelFactory._resolve_api_key", return_value="ai-test")
    def test_create_gemini_model(self, _mock_key):
        config = _config(LlmModelConfig(
            name="default", provider=LlmProvider.GEMINI, model_name="gemini-3-flash-preview", timeout=120,
        ))
        model = ModelFactory.create_model(config)
        self.assertIsInstance(model, LangChainGeminiAdapter)

    @patch("src.llm.model_factory.ModelFactory._resolve_api_key", return_value="gsk-test")
    def test_create_groq_model(self, _mock_key):
        config = _config(LlmModelConfig(
            name="default", provider=LlmProvider.GROQ, model_name="llama-3.3-70b-versatile", timeout=120,
        ))
        model = ModelFactory.create_model(config)
        self.assertIsInstance(model, LangChainGroqAdapter)

    def test_selects_model_by_name(self):
        config = _config(
            LlmModelConfig(name="local", provider=LlmProvider.OLLAMA, model_name="llama3.2"),
            LlmModelConfig(name="cloud", provider=LlmProvider.GROQ, model_name="llama-3.3", default=True),
        )
        self.assertIsInstance(ModelFactory.create_model(config, model_name="cloud"), LangChainGroqAdapter)

    def test_gets_model_by_name(self):
        config = _config(
            LlmModelConfig(name="local", provider=LlmProvider.OLLAMA, model_name="llama3.2"),
            LlmModelConfig(name="cloud", provider=LlmProvider.GROQ, model_name="llama-3.3"),
        )
        self.assertEqual(config.get_model("cloud").name, "cloud")
        self.assertEqual(config.default_model.name, "local")

    def test_get_model_unknown_raises(self):
        config = _config(LlmModelConfig(name="default", provider=LlmProvider.OLLAMA, model_name="llama3.2"))
        with self.assertRaises(ValueError):
            ModelFactory.create_model(config, model_name="does-not-exist")

    def test_resolve_api_key_from_custom_env_var(self):
        model = LlmModelConfig(
            name="default", provider=LlmProvider.DEEPSEEK, model_name="deepseek-chat", api_key_env="MY_DEEPSEEK_KEY",
        )
        with patch.dict("os.environ", {"MY_DEEPSEEK_KEY": "sk-from-custom"}, clear=True):
            self.assertEqual(
                ModelFactory._resolve_api_key(model, "LLM_PROVIDER__DEEPSEEK__API_KEY", "DeepSeek"),
                "sk-from-custom",
            )

    @patch.dict("os.environ", {"LLM_PROVIDER__DEEPSEEK__API_KEY": "sk-from-env"}, clear=True)
    @patch("src.llm.model_factory.load_dotenv")
    def test_resolve_api_key_from_default_env_var(self, mock_load_dotenv):
        model = LlmModelConfig(name="default", provider=LlmProvider.DEEPSEEK, model_name="deepseek-chat")
        self.assertEqual(
            ModelFactory._resolve_api_key(model, "LLM_PROVIDER__DEEPSEEK__API_KEY", "DeepSeek"),
            "sk-from-env",
        )
        mock_load_dotenv.assert_called_once()

    @patch.dict("os.environ", {}, clear=True)
    @patch("src.llm.model_factory.load_dotenv")
    def test_resolve_api_key_missing_raises(self, _mock_load_dotenv):
        model = LlmModelConfig(name="default", provider=LlmProvider.DEEPSEEK, model_name="deepseek-chat")
        with self.assertRaises(ValueError):
            ModelFactory._resolve_api_key(model, "LLM_PROVIDER__DEEPSEEK__API_KEY", "DeepSeek")


if __name__ == "__main__":
    unittest.main()