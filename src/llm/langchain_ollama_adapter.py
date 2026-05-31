from typing import Any, List

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama

from src.core.interfaces.llm_adapter import LlmAdapter


class LangChainOllamaAdapter(LlmAdapter):
    def __init__(self, model_name: str, base_url: str, temperature: float = 0.0):
        self._model = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=temperature,
        )
        self._tools = []
        self._bound_model = self._model

    def bind_tools(self, tools: List[Any]) -> None:
        self._tools = tools
        self._bound_model = self._model.bind_tools(tools)

    def generate(self, prompt: str) -> str:
        system_message = """
            You are an AI quantitative trading analyst responsible for analyzing financial assets.
            You have access to the `get_trading_context` tool, which provides market data, technical indicators, fundamentals, 
            sentiment, portfolio information, positions, and other trading-related context.
            
            Guidelines:
            - Use `get_trading_context` whenever additional information is needed to complete the task.
            - When analyzing multiple assets, call `get_trading_context` separately for each asset. Never pass multiple assets in a single tool call.
            - Base conclusions only on available data and tool results.
            - Do not invent facts, prices, indicators, positions, or market conditions.
            - Clearly identify uncertainty, missing information, and conflicting signals.
            - Adapt your output format and level of detail to the user's request.
            - Be concise, objective, and evidence-driven.
        """
        messages: list[BaseMessage] = [HumanMessage(content=prompt), SystemMessage(content=system_message)]
        response = self._bound_model.invoke(messages)

        if hasattr(response, 'tool_calls') and response.tool_calls:
            messages.append(response)
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"].lower()
                selected_tool = next((t for t in self._tools if t.name.lower() == tool_name), None)
                if selected_tool:
                    tool_output = selected_tool.invoke(tool_call["args"])
                    messages.append(ToolMessage(content=str(tool_output), tool_call_id=tool_call["id"]))

            response = self._bound_model.invoke(messages)

        return response.content
