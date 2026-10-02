import unittest
from unittest.mock import MagicMock, patch

from src.configuration.llm_config import (
    LlmConfig,
    LlmModelConfig,
    LlmProvider,
    ToolConfig,
    ToolRegistryConfig,
)
from src.entities.llm_credential import LlmCredential
from src.llm.llm_runtime_manager import LlmRuntimeManager


class TestLlmRuntimeManager(unittest.TestCase):
    def setUp(self):
        self.config = LlmConfig.model_construct(
            models=[
                LlmModelConfig(
                    id="groq-qwen",
                    name="Groq Qwen",
                    provider=LlmProvider.GROQ,
                    model_name="qwen/qwen3.8-27b",
                    default=True,
                ),
                LlmModelConfig(
                    id="gemini-3-flash",
                    name="Gemini 3 Flash",
                    provider=LlmProvider.GEMINI,
                    model_name="gemini-3-flash-preview",
                    default=False,
                ),
                LlmModelConfig(
                    id="ollama-local",
                    name="Ollama Local",
                    provider=LlmProvider.OLLAMA,
                    model_name="llama3.2",
                    default=False,
                ),
            ],
            tools=ToolRegistryConfig(
                bot_tools=[
                    ToolConfig(name="trading_context", enabled=True, description="Market context"),
                ]
            ),
        )
        self.db_manager = MagicMock()

    @patch("src.llm.llm_runtime_manager.ModelFactory.create_model")
    def test_initialization_defaults_to_default_model(self, mock_create_model):
        mock_adapter = MagicMock()
        mock_create_model.return_value = mock_adapter

        # DB has no active model
        uow = MagicMock()
        repo = MagicMock()
        repo.get_active.return_value = None
        repo.get_by_model_id.return_value = None
        repo.get_all.return_value = []
        uow.get_repository.return_value = repo
        self.db_manager.get_unit_of_work.return_value.__enter__.return_value = uow

        manager = LlmRuntimeManager(self.config, self.db_manager)

        self.assertEqual(manager.active_model_id, "groq-qwen")
        mock_create_model.assert_called_once()

    @patch("src.llm.llm_runtime_manager.ModelFactory.create_model")
    def test_switch_active_model(self, mock_create_model):
        mock_adapter = MagicMock()
        mock_create_model.return_value = mock_adapter

        uow = MagicMock()
        repo = MagicMock()
        repo.get_active.return_value = LlmCredential(
            model_id="gemini-3-flash", provider="gemini", is_active=True
        )
        repo.get_by_model_id.return_value = LlmCredential(
            model_id="gemini-3-flash", provider="gemini", api_key="gemini-key", is_active=True
        )
        uow.get_repository.return_value = repo
        self.db_manager.get_unit_of_work.return_value.__enter__.return_value = uow

        manager = LlmRuntimeManager(self.config, self.db_manager)
        result = manager.switch_active_model("gemini-3-flash")

        self.assertEqual(result["active_model_id"], "gemini-3-flash")
        self.assertEqual(manager.active_model_id, "gemini-3-flash")

    @patch("src.llm.llm_runtime_manager.ModelFactory.create_model")
    def test_dynamic_proxy_adapter_delegation(self, mock_create_model):
        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = "AI response"
        mock_create_model.return_value = mock_adapter

        uow = MagicMock()
        repo = MagicMock()
        repo.get_active.return_value = None
        repo.get_by_model_id.return_value = None
        uow.get_repository.return_value = repo
        self.db_manager.get_unit_of_work.return_value.__enter__.return_value = uow

        manager = LlmRuntimeManager(self.config, self.db_manager)
        proxy = manager.proxy_adapter

        response = proxy.generate(prompt="Hello")
        self.assertEqual(response, "AI response")
        mock_adapter.generate.assert_called_once_with(
            prompt="Hello", history=None, system_prompt=None
        )

    @patch("src.llm.llm_runtime_manager.ModelFactory.create_model")
    def test_list_models_and_tools_status(self, mock_create_model):
        mock_create_model.return_value = MagicMock()

        uow = MagicMock()
        repo = MagicMock()
        repo.get_active.return_value = None
        repo.get_by_model_id.return_value = None
        repo.get_all.return_value = [
            LlmCredential(
                model_id="groq-qwen", provider="groq", api_key="gsk-12345678", is_active=True
            )
        ]
        uow.get_repository.return_value = repo
        self.db_manager.get_unit_of_work.return_value.__enter__.return_value = uow

        manager = LlmRuntimeManager(self.config, self.db_manager)
        models = manager.list_models_status()

        self.assertEqual(len(models), 3)
        groq_status = next(m for m in models if m["id"] == "groq-qwen")
        self.assertTrue(groq_status["has_api_key"])
        self.assertEqual(groq_status["masked_api_key"], "••••••••5678")

        tools = manager.list_tools_status()
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "trading_context")


if __name__ == "__main__":
    unittest.main()
