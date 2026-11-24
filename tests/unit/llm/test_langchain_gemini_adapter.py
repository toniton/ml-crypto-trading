import asyncio
import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessageChunk

from src.llm import LangChainGeminiAdapter
from src.llm.base_langchain_adapter import BaseLangChainAdapter


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
            max_output_tokens=None,
            thinking_budget=0,
        )

    @patch("src.llm.langchain_gemini_adapter.ChatGoogleGenerativeAI")
    def test_generate_with_timeout_base_url_and_max_tokens(self, mock_chat_gemini):
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
            max_tokens=1024,
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
            max_output_tokens=1024,
            thinking_budget=0,
        )

    @patch("src.llm.langchain_gemini_adapter.ChatGoogleGenerativeAI")
    def test_generate_extracts_text_from_content_blocks(self, mock_chat_gemini):
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            {"type": "thinking", "thinking": "Internal reasoning"},
            {"type": "text", "text": "BTC_USD is "},
            {"type": "text", "text": "flat."},
        ]
        mock_response.tool_calls = []
        mock_instance.invoke.return_value = mock_response
        mock_chat_gemini.return_value = mock_instance

        adapter = LangChainGeminiAdapter(model_name="gemini-3-flash-preview", api_key="ai-test")
        self.assertEqual(adapter.generate("Status?"), "BTC_USD is flat.")

    @patch("src.llm.langchain_gemini_adapter.ChatGoogleGenerativeAI")
    def test_stream_extracts_text_from_content_blocks(self, mock_chat_gemini):
        chunks = [
            AIMessageChunk(content=[{"type": "thinking", "thinking": "Hidden"}]),
            AIMessageChunk(content=[{"type": "text", "text": "Hello "}]),
            AIMessageChunk(content=[{"type": "text", "text": "Gemini!"}]),
        ]

        async def fake_astream(_messages):
            for chunk in chunks:
                yield chunk

        mock_instance = MagicMock()
        mock_instance.astream.side_effect = fake_astream
        mock_chat_gemini.return_value = mock_instance

        adapter = LangChainGeminiAdapter(model_name="gemini-3-flash-preview", api_key="ai-test")
        result = asyncio.run(collect_stream(adapter, "Say hello"))
        self.assertEqual(result, ["Hello ", "Gemini!"])

    def test_non_recoverable_provider_error_detects_gemini_errors(self):
        for message in (
            "429 RESOURCE_EXHAUSTED: Quota exceeded for metric",
            "400 API_KEY_INVALID: API key not valid.",
            "403 PERMISSION_DENIED: Caller does not have permission",
        ):
            self.assertTrue(
                BaseLangChainAdapter.is_non_recoverable_provider_error(RuntimeError(message)),
                msg=f"Expected non-recoverable error for: {message}",
            )
        self.assertFalse(
            BaseLangChainAdapter.is_non_recoverable_provider_error(RuntimeError("temporary network timeout"))
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