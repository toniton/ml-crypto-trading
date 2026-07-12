import unittest
from unittest.mock import MagicMock, patch

from src.llm.langchain_ollama_adapter import LangChainOllamaAdapter


class TestLangChainOllamaAdapter(unittest.TestCase):
    @patch('src.llm.langchain_ollama_adapter.ChatOllama')
    def test_generate(self, mock_chat_ollama):
        # Setup
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.tool_calls = []
        mock_instance.invoke.return_value = mock_response
        mock_chat_ollama.return_value = mock_instance

        adapter = LangChainOllamaAdapter(model_name="test-model", base_url="http://test")

        # Execute
        response = adapter.generate("Hello")

        # Verify
        self.assertEqual(response, "Test response")
        mock_instance.invoke.assert_called_once()
        mock_chat_ollama.assert_called_once_with(
            model="test-model",
            base_url="http://test",
            temperature=0.0,
        )
