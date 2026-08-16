import asyncio
import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessageChunk

from src.llm import LangChainGeminiAdapter


async def collect_stream(adapter, prompt):
    return [chunk async for chunk in adapter.stream(prompt)]


class TestLangChainGeminiAdapter(unittest.TestCase):
    @patch("src.llm.langchain_gemini_adapter.ChatGoogleGenerativeAI")
    def test_generate(self, mock_chat_gemini):
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.tool_calls = []
        mock_instance.invoke.return_value = mock_response
        mock_chat_gemini.return_value = mock_instance

        adapter = LangChainGeminiAdapter(model_name="gemini-3-flash-preview", api_key="ai-test")
        response = adapter.generate("Hello")

        self.assertEqual(response, "Test response")
        mock_instance.invoke.assert_called_once()
        mock_chat_gemini.assert_called_once_with(
            model="gemini-3-flash-preview",
            google_api_key="ai-test",
            base_url=None,
            temperature=0.0,
            timeout=60.0,
            max_retries=2,
            thinking_budget=0,
        )

    @patch("src.llm.langchain_gemini_adapter.ChatGoogleGenerativeAI")
    def test_generate_with_timeout_and_base_url(self, mock_chat_gemini):
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.tool_calls = []
        mock_instance.invoke.return_value = mock_response
        mock_chat_gemini.return_value = mock_instance

        adapter = LangChainGeminiAdapter(
            model_name="gemini-3-flash-preview",
            api_key="ai-test",
            timeout=30.0,
            base_url="https://custom.gemini.test/v1",
        )
        response = adapter.generate("Hello")

        self.assertEqual(response, "Test response")
        mock_chat_gemini.assert_called_once_with(
            model="gemini-3-flash-preview",
            google_api_key="ai-test",
            base_url="https://custom.gemini.test/v1",
            temperature=0.0,
            timeout=30.0,
            max_retries=2,
            thinking_budget=0,
        )

    @patch("src.llm.langchain_gemini_adapter.ChatGoogleGenerativeAI")
    def test_stream_simple_tokens(self, mock_chat_gemini):
        chunk1 = AIMessageChunk(content="Hello ")
        chunk2 = AIMessageChunk(content="world!")

        async def fake_astream(_messages):
            for c in [chunk1, chunk2]:
                yield c

        mock_instance = MagicMock()
        mock_instance.astream.side_effect = fake_astream
        mock_chat_gemini.return_value = mock_instance

        adapter = LangChainGeminiAdapter(model_name="gemini-3-flash-preview", api_key="ai-test")
        result = asyncio.run(collect_stream(adapter, "Say hello"))
        self.assertEqual(result, ["Hello ", "world!"])

    @patch("src.llm.langchain_gemini_adapter.ChatGoogleGenerativeAI")
    def test_generate_with_tool_calls(self, mock_chat_gemini):
        mock_instance = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "get_exchange_fees"
        mock_tool.invoke.return_value = "maker_fee: 0.1%"

        tool_response = MagicMock()
        tool_response.content = ""
        tool_response.tool_calls = [
            {"name": "get_exchange_fees", "args": {"ticker_symbol": "BTC_USD"}, "id": "call_1"}
        ]

        final_response = MagicMock()
        final_response.content = "The maker fee is 0.1%."
        final_response.tool_calls = []

        mock_bound_instance = MagicMock()
        mock_bound_instance.invoke.side_effect = [tool_response, final_response]
        mock_instance.bind_tools.return_value = mock_bound_instance
        mock_chat_gemini.return_value = mock_instance

        adapter = LangChainGeminiAdapter(model_name="gemini-3-flash-preview", api_key="ai-test")
        adapter.bind_tools([mock_tool])

        response = adapter.generate("Get fees for BTC")
        self.assertEqual(response, "The maker fee is 0.1%.")
        mock_tool.invoke.assert_called_once_with({"ticker_symbol": "BTC_USD"})


if __name__ == "__main__":
    unittest.main()