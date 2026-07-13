from typing import List

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama

from src.core.interfaces.llm_adapter import LlmAdapter


class LangChainOllamaAdapter(LlmAdapter):
    def __init__(self, model_name: str, base_url: str, temperature: float = 0.0, timeout: float | None = None):
        client_kwargs = {}
        if timeout is not None:
            client_kwargs["timeout"] = timeout
        self._model = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=temperature,
            client_kwargs=client_kwargs,
        )
        self._tool_lookup = {}
        self._bound_model = self._model

    def bind_tools(self, tools: List[BaseTool]) -> None:
        self._tool_lookup = {
            tool.name.lower(): tool
            for tool in tools
        }
        self._bound_model = self._model.bind_tools(tools)

    def generate(self, prompt: str) -> str:
        system_message = """
            You are an AI quantitative trading analyst responsible for analyzing financial assets.
            You have access to the following tools:
            - `get_trading_context`: Returns current balances, positions, entry/exit prices, and realized PnL for a single asset.
            - `get_exchange_fees`: Returns exchange fee schedules (maker/taker fees) for a single asset.
            - `get_market_statistics`: Returns the latest market statistics (close, high, low, 24h volume) for a single asset.
            
            Guidelines:
            - Use these tools whenever additional information is needed to complete the task.
            - When analyzing multiple assets, call these tools separately for each individual asset. Never pass multiple assets in a single tool call.
            - Base conclusions only on available data and tool results.
            - Do not invent facts, prices, indicators, positions, or market conditions.
            - Clearly identify uncertainty, missing information, and conflicting signals.
            - Adapt your output format and level of detail to the user's request.
            - Be concise, objective, and evidence-driven.
            - Never answer using assumed tool outputs. If a required tool fails or is unavailable, explain that the information could not be retrieved.
        """
        messages: list[BaseMessage] = [SystemMessage(content=system_message), HumanMessage(content=prompt)]

        max_turns = 5
        for _turn in range(max_turns):
            response = self._bound_model.invoke(messages)

            if hasattr(response, 'tool_calls') and response.tool_calls:
                messages.append(response)
                # Execute all tool calls in the current turn
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"].lower()
                    selected_tool = self._tool_lookup.get(tool_name)
                    if selected_tool:
                        try:
                            tool_output = selected_tool.invoke(tool_call["args"])
                        except Exception as e:
                            tool_output = f"Tool execution failed: {e}"
                    else:
                        tool_output = f"Unknown tool: {tool_name}"

                    messages.append(ToolMessage(content=str(tool_output), tool_call_id=tool_call["id"]))
                # Continue loop to let LLM process tool outputs
                continue
            return response.content

        # If we reached max turns, invoke one last time to get the final text response without tool calls
        final_response = self._bound_model.invoke(messages)
        return final_response.content
