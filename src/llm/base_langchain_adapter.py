from __future__ import annotations

import asyncio
import json
from abc import ABC
from typing import Any, AsyncIterator, Dict, List, Type, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.ai import ToolCall
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ValidationError

from src.core.interfaces.llm_adapter import LlmAdapter

Structured = TypeVar("Structured", bound=BaseModel)

# Order matters: the first method a provider accepts wins.
STRUCTURED_OUTPUT_METHODS = ("function_calling", "json_schema", "json_mode")

SYSTEM_PROMPT = """
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


class BaseLangChainAdapter(LlmAdapter, ABC):
    """Shared tool-calling loop for LangChain chat model integrations."""

    def __init__(self, max_turns: int = 5, system_prompt: str | None = None):
        self._tool_lookup: Dict[str, BaseTool] = {}
        self._model: Any = None
        self._bound_model: Any = None
        self._max_turns = max_turns
        self._system_prompt = system_prompt or SYSTEM_PROMPT

    def bind_tools(self, tools: List[BaseTool]) -> None:
        self._tool_lookup = {
            tool.name.lower(): tool
            for tool in tools
        }
        self._bound_model = self._model.bind_tools(tools)

    def _execute_tool_calls(self, tool_calls: List[ToolCall], messages: List[BaseMessage]) -> None:
        """Executes a list of tool calls and appends corresponding ToolMessages to messages."""
        for tool_call in tool_calls:
            tool_name = tool_call.get("name", "").lower()
            selected_tool = self._tool_lookup.get(tool_name)
            tool_id = tool_call.get("id", "")
            tool_args = tool_call.get("args", {})

            if selected_tool:
                try:
                    tool_output = selected_tool.invoke(tool_args)
                except Exception as e:  # pylint: disable=broad-except
                    tool_output = f"Tool execution failed: {e}"
            else:
                tool_output = f"Unknown tool: {tool_name}"

            messages.append(ToolMessage(content=str(tool_output), tool_call_id=tool_id))

    def generate(self, prompt: str) -> str:
        messages: list[BaseMessage] = [SystemMessage(content=self._system_prompt), HumanMessage(content=prompt)]

        for _turn in range(self._max_turns):
            response = self._bound_model.invoke(messages)

            if hasattr(response, "tool_calls") and response.tool_calls:
                messages.append(response)
                self._execute_tool_calls(response.tool_calls, messages)
                continue
            return response.content

        final_response = self._bound_model.invoke(messages)
        return final_response.content

    def generate_structured(self, schema: Type[Structured], prompt: str, system_prompt: str) -> Structured:
        messages: list[BaseMessage] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ]
        errors: List[str] = []
        for method in STRUCTURED_OUTPUT_METHODS:
            try:
                structured_model = self._model.with_structured_output(schema, method=method)
                result = structured_model.invoke(messages)
                return self._coerce_structured_result(schema, result)
            except Exception as exc:  # pylint: disable=broad-except
                errors.append(f"{method}: {exc}")

        # Last resort: instruct the model to emit a bare JSON object and parse it.
        try:
            json_prompt = (
                "Respond with a single valid JSON object matching this schema. "
                "Do not include any markdown, prose, or commentary.\n\n"
                f"SCHEMA:\n{schema.model_json_schema()}\n\n{prompt}"
            )
            result = self._model.invoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=json_prompt)]
            )
            return self._parse_json_fallback(schema, result)
        except Exception as exc:  # pylint: disable=broad-except
            errors.append(f"json-instruct: {exc}")

        raise ValueError(
            f"Structured output failed for every method for {schema.__name__}. "
            + "; ".join(errors)
        )

    def _coerce_structured_result(self, schema: Type[Structured], result: Any) -> Structured:
        if isinstance(result, schema):
            return result
        if isinstance(result, dict):
            return schema(**result)
        return self._parse_json_fallback(schema, result)

    def _parse_json_fallback(self, schema: Type[Structured], result: Any) -> Structured:
        """Parses a structured output from raw model content when the provider does not
        support native structured output (e.g. local Ollama models)."""
        content = result.content if hasattr(result, "content") else result
        if isinstance(content, list):
            content = "".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in content
            )
        parsed = self._extract_json_object(str(content))
        try:
            return schema(**parsed)
        except ValidationError as exc:
            raise ValueError(
                f"Model did not return a valid {schema.__name__}: {exc}"
            ) from exc

    @staticmethod
    def _extract_json_object(text: str) -> Any:
        fenced = text.strip()
        if fenced.startswith("```"):
            lines = fenced.splitlines()
            if lines:
                lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
            fenced = "\n".join(lines).strip()
        return json.loads(fenced)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        messages: list[BaseMessage] = [SystemMessage(content=self._system_prompt), HumanMessage(content=prompt)]

        for _turn in range(self._max_turns):
            accumulated: Any = None
            async for chunk in self._bound_model.astream(messages):
                if hasattr(chunk, "content") and chunk.content:
                    yield str(chunk.content)
                accumulated = chunk if accumulated is None else accumulated + chunk

            if accumulated and hasattr(accumulated, "tool_calls") and accumulated.tool_calls:
                messages.append(accumulated)
                await asyncio.to_thread(self._execute_tool_calls, accumulated.tool_calls, messages)
                continue
            break
