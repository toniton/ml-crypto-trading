import asyncio
import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessageChunk

from src.llm import LangChainOpenCodeAdapter, OPENCODE_API_BASE
from src.llm.base_langchain_adapter import BaseLangChainAdapter


async def collect_stream(adapter, prompt):
    return [chunk async for chunk in adapter.stream(prompt)]


class TestLangChainOpenCodeAdapter(unittest.TestCase):
    @patch("src.llm.langchain_opencode_adapter.ChatOpenAI")
    def test_generate_returns_model_response(self, mock_chat_openai):
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.tool_calls = []
        mock_instance.invoke.return_value = mock_response
        mock_chat_openai.return_value = mock_instance

        adapter = LangChainOpenCodeAdapter(model_name="big-pickle", api_key="oc-test")

        self.assertEqual(adapter.generate("Hello"), "Test response")

    @patch("src.llm.langchain_opencode_adapter.ChatOpenAI")
    def test_init_uses_default_opencode_base_url(self, mock_chat_openai):
        LangChainOpenCodeAdapter(model_name="deepseek-v4.1-flash-free", api_key="oc-test", session_id="sess-1")

        mock_chat_openai.assert_called_once_with(
            model="deepseek-v4.1-flash-free",
            api_key="oc-test",
            base_url=OPENCODE_API_BASE,
            temperature=0.0,
            request_timeout=60.0,
            max_retries=2,
            default_headers={
                "x-opencode-session": "sess-1",
                "User-Agent": BaseLangChainAdapter.USER_AGENT,
            },
        )

    @patch("src.llm.langchain_opencode_adapter.ChatOpenAI")
    def test_init_forwards_custom_timeout_base_url_and_max_tokens(self, mock_chat_openai):
        LangChainOpenCodeAdapter(
            model_name="deepseek-v4.1-flash-free",
            api_key="oc-test",
            timeout=30.0,
            base_url="https://custom.opencode.test/v1",
            max_tokens=1024,
            session_id="sess-2",
        )

        mock_chat_openai.assert_called_once_with(
            model="deepseek-v4.1-flash-free",
            api_key="oc-test",
            base_url="https://custom.opencode.test/v1",
            temperature=0.0,
            request_timeout=30.0,
            max_retries=2,
            default_headers={
                "x-opencode-session": "sess-2",
                "User-Agent": BaseLangChainAdapter.USER_AGENT,
            },
            max_tokens=1024,
        )

    def test_user_agent_inherited_from_base_adapter(self):
        self.assertEqual(LangChainOpenCodeAdapter.USER_AGENT, BaseLangChainAdapter.USER_AGENT)

    @patch("src.llm.langchain_opencode_adapter.ChatOpenAI")
    def test_init_generates_session_header_when_not_provided(self, mock_chat_openai):
        LangChainOpenCodeAdapter(model_name="deepseek-v4.1-flash-free", api_key="oc-test")

        _, kwargs = mock_chat_openai.call_args
        self.assertTrue(bool(kwargs["default_headers"]["x-opencode-session"]))

    @patch("src.llm.langchain_opencode_adapter.ChatOpenAI")
    def test_stream_simple_tokens(self, mock_chat_openai):
        chunk1 = AIMessageChunk(content="Hello ")
        chunk2 = AIMessageChunk(content="world!")

        async def fake_astream(_messages):
            for chunk in [chunk1, chunk2]:
                yield chunk

        mock_instance = MagicMock()
        mock_instance.astream.side_effect = fake_astream
        mock_chat_openai.return_value = mock_instance

        adapter = LangChainOpenCodeAdapter(model_name="big-pickle", api_key="oc-test")
        result = asyncio.run(collect_stream(adapter, "Say hello"))

        self.assertEqual(result, ["Hello ", "world!"])

    @patch("src.llm.langchain_opencode_adapter.ChatOpenAI")
    def test_generate_with_tool_calls(self, mock_chat_openai):
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
        mock_chat_openai.return_value = mock_instance

        adapter = LangChainOpenCodeAdapter(model_name="big-pickle", api_key="oc-test")
        adapter.bind_tools([mock_tool])

        self.assertEqual(adapter.generate("Get fees for BTC"), "The maker fee is 0.1%.")


if __name__ == "__main__":
    unittest.main()
