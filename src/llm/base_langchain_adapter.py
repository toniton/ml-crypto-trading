from __future__ import annotations

import asyncio
import json
import re
from abc import ABC
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional, Type, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.ai import ToolCall
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ValidationError

from src.core.interfaces.llm_adapter import ChatTurn, LlmAdapter

Structured = TypeVar("Structured", bound=BaseModel)

# Order matters: the first method a provider accepts wins.
STRUCTURED_OUTPUT_METHODS = ("function_calling", "json_schema", "json_mode")

SYSTEM_PROMPT = """
You are the AI quantitative trading and operations analyst for **Rio**, an autonomous algorithmic cryptocurrency trading platform (trading pairs such as BTC_USD, ETH_USD, CRO_USD, SOL_USD on exchanges like CRYPTO_DOT_COM).
IMPORTANT: "Rio" ALWAYS refers to this algorithmic crypto trading bot and platform — NEVER to Rio Tinto plc (NYSE/LSE: RIO) or any mining company.

Guidelines:
- Base conclusions strictly on available tool outputs, telemetry, and provided context.
- Preserve exact identifiers (e.g. order IDs, decision IDs, tick IDs, experiment IDs, candidate IDs, commit hashes, retention run/policy IDs), timestamps, percentages, dollar amounts, and sizing formulas from the retrieved evidence.
- Do not invent facts, prices, indicators, positions, or market conditions.
- Clearly identify uncertainty, missing information, low sample sizes, and conflicting signals.
- Maintain strict epistemic honesty:
  * Distinguish a healthy bot process from active trading across all assets.
  * Distinguish authoritative exchange balance from locally reserved cash in open orders.
  * Distinguish realized closed-trade P&L from unrealized mark-to-market P&L.
  * Distinguish in-sample/exploratory backtest winners from out-of-sample walk-forward robustness.
  * Frame configuration recommendations as hypotheses requiring human operator approval, not proof of guaranteed future performance.
- Never answer using assumed data. If required information or a commit/order reference is unavailable, state clearly that it is unavailable rather than substituting current state.
- Write every calculation as ONE single-line formula, not split across lines. Wrap each formula in $$ ... $$ and put it on its own paragraph with a blank line before and after so it renders as a block.
  Keep currency amounts (e.g. $64,249.78), units, and short narrative terms like P close in ordinary text; inside math use \\text{...} only for symbols such as \\text{BTC} and never write a bare $ inside a formula (escape it as \\$ if truly needed).
"""


class BaseLangChainAdapter(LlmAdapter, ABC):
    """Shared tool-calling loop for LangChain chat model integrations."""

    def __init__(self, max_turns: int = 5, system_prompt: str | None = None):
        self._tool_lookup: Dict[str, BaseTool] = {}
        self._model: Any = None
        self._bound_model: Any = None
        self._max_turns = max_turns
        self._system_prompt = system_prompt or SYSTEM_PROMPT
        self._preferred_structured_method: Optional[str] = None

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def bind_tools(  # pylint: disable=too-many-branches,too-many-locals
        self,
        tools: List[BaseTool] | Mapping[str, Any],
    ) -> None:
        if isinstance(tools, Mapping):
            tool_items = list(tools.items())
            tool_list = list(tools.values())
        else:
            tool_items = [(getattr(t, "name", str(t)), t) for t in tools]
            tool_list = list(tools)

        lookup: Dict[str, Any] = {}
        raw_tools: List[BaseTool] = []
        seen_raw_names: set[str] = set()

        for alias, tool in tool_items:
            lookup[str(alias).lower()] = tool
            tool_name = getattr(tool, "name", str(alias)).lower()
            lookup[tool_name] = tool
            key_name = getattr(tool, "_key_name", None)
            if key_name:
                lookup[str(key_name).lower()] = tool
            if tool_name == "backtest" or str(alias).lower() == "backtest":
                lookup["run_backtest"] = tool
                lookup["backtest"] = tool
            if tool_name == "get_account_balance" or str(alias).lower() == "account_balance":
                lookup["account_balance"] = tool
                lookup["get_account_balance"] = tool
            for short_alias, full_name in (
                ("open_orders", "get_open_orders"),
                ("exchange_read", "exchange_read_api"),
                ("metrics", "query_metrics"),
                ("trade_attribution", "get_trade_attribution"),
                ("configuration", "get_configuration"),
                ("configuration_history", "get_configuration_history"),
                ("backtest_drift", "detect_backtest_drift"),
                ("trading_context", "get_trading_context"),
                ("session_summary", "get_session_summary"),
            ):
                if tool_name in (short_alias, full_name) or str(alias).lower() in (short_alias, full_name):
                    lookup[short_alias] = tool
                    lookup[full_name] = tool

            raw_tool = getattr(tool, "_tool", tool)
            raw_name = getattr(raw_tool, "name", str(alias))
            is_mock = type(raw_tool).__module__.startswith("unittest.mock")
            if isinstance(raw_tool, BaseTool) and not is_mock and raw_name not in seen_raw_names:
                raw_tools.append(raw_tool)
                seen_raw_names.add(raw_name)

        self._tool_lookup = lookup
        if self._model is not None:
            if isinstance(tools, Mapping):
                self._bound_model = self._model
            elif raw_tools:
                try:
                    self._bound_model = self._model.bind_tools(raw_tools)
                except Exception:  # pylint: disable=broad-except
                    self._bound_model = self._model
            elif tool_list:
                try:
                    self._bound_model = self._model.bind_tools(tool_list)
                except Exception:  # pylint: disable=broad-except
                    self._bound_model = self._model
            else:
                self._bound_model = self._model

    def get_tool(self, name: str) -> BaseTool | None:
        return self._tool_lookup.get(name.lower())

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

    def _build_messages(
            self,
            prompt: str,
            history: List[ChatTurn] | None = None,
            system_prompt: Optional[str] = None,
    ) -> list[BaseMessage]:
        effective_system_prompt = system_prompt or self._system_prompt
        messages: list[BaseMessage] = [SystemMessage(content=effective_system_prompt)]
        for turn in history or []:
            if turn.role == "assistant":
                messages.append(AIMessage(content=turn.content))
            else:
                messages.append(HumanMessage(content=turn.content))
        messages.append(HumanMessage(content=prompt))
        return messages

    def generate(
            self,
            prompt: str,
            history: List[ChatTurn] | None = None,
            system_prompt: Optional[str] = None,
    ) -> str:
        messages: list[BaseMessage] = self._build_messages(prompt, history, system_prompt=system_prompt)
        active_model = self._bound_model if self._bound_model is not None else self._model

        for _turn in range(self._max_turns):
            response = active_model.invoke(messages)

            try:
                tool_calls = response.tool_calls
            except AttributeError:
                tool_calls = None

            if tool_calls:
                messages.append(response)
                self._execute_tool_calls(tool_calls, messages)
                continue
            return self._strip_thinking_tags(str(response.content))

        final_response = active_model.invoke(messages)
        return self._strip_thinking_tags(str(final_response.content))

    def generate_structured(self, schema: Type[Structured], prompt: str, system_prompt: str) -> Structured:
        messages: list[BaseMessage] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ]
        errors: List[str] = []

        if self._preferred_structured_method == "json-instruct":
            try:
                return self._invoke_json_instruct(schema, prompt, system_prompt)
            except Exception as exc:  # pylint: disable=broad-except
                errors.append(f"json-instruct (cached): {exc}")
                self._preferred_structured_method = None

        methods_to_try = list(STRUCTURED_OUTPUT_METHODS)
        if self._preferred_structured_method in methods_to_try:
            methods_to_try.remove(self._preferred_structured_method)
            methods_to_try.insert(0, self._preferred_structured_method)

        for method in methods_to_try:
            try:
                structured_model = self._model.with_structured_output(schema, method=method)
                result = structured_model.invoke(messages)
                coerced = self._coerce_structured_result(schema, result)
                self._preferred_structured_method = method
                return coerced
            except Exception as exc:  # pylint: disable=broad-except
                if self._is_non_recoverable_provider_error(exc):
                    raise ValueError(
                        f"Structured output aborted due to provider error for {schema.__name__} ({method}): {exc}"
                    ) from exc
                errors.append(f"{method}: {exc}")

        # Last resort: instruct the model to emit a bare JSON object and parse it.
        try:
            coerced = self._invoke_json_instruct(schema, prompt, system_prompt)
            self._preferred_structured_method = "json-instruct"
            return coerced
        except Exception as exc:  # pylint: disable=broad-except
            errors.append(f"json-instruct: {exc}")

        raise ValueError(
            f"Structured output failed for every method for {schema.__name__}. "
            + "; ".join(errors)
        )

    @staticmethod
    def is_non_recoverable_provider_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(
            marker in msg
            for marker in (
                "error code: 402",
                "insufficient balance",
                "error code: 401",
                "invalid_api_key",
                "error code: 429",
                "rate_limit_exceeded",
            )
        )

    @classmethod
    def _is_non_recoverable_provider_error(cls, exc: Exception) -> bool:
        return cls.is_non_recoverable_provider_error(exc)

    def _invoke_json_instruct(self, schema: Type[Structured], prompt: str, system_prompt: str) -> Structured:
        json_prompt = (
            "Respond with a single valid JSON object matching this schema. "
            "Do not include any markdown, prose, or commentary.\n\n"
            f"SCHEMA:\n{schema.model_json_schema()}\n\n{prompt}"
        )
        result = self._model.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=json_prompt)]
        )
        return self._parse_json_fallback(schema, result)

    def _coerce_structured_result(self, schema: Type[Structured], result: Any) -> Structured:
        if isinstance(result, schema):
            return result
        if isinstance(result, dict):
            return schema(**result)
        return self._parse_json_fallback(schema, result)

    def _parse_json_fallback(self, schema: Type[Structured], result: Any) -> Structured:
        """Parses a structured output from raw model content when the provider does not
        support native structured output (e.g. local Ollama models)."""
        try:
            content = result.content
        except AttributeError:
            content = result
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
    def _strip_thinking_tags(text: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        normalized = (
            cleaned.replace("\u2011", "-")
            .replace("\u2010", "-")
            .replace("\u202f", " ")
            .replace("\u00a0", " ")
        )
        return normalized.strip() if normalized != text else text

    @classmethod
    def _extract_json_object(cls, text: str) -> Any:
        fenced = cls._strip_thinking_tags(text).strip()
        if fenced.startswith("```"):
            lines = fenced.splitlines()
            if lines:
                lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
            fenced = "\n".join(lines).strip()
        try:
            return json.loads(fenced)
        except json.JSONDecodeError:
            start_idx = fenced.find("{")
            end_idx = fenced.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                return json.loads(fenced[start_idx: end_idx + 1])
            raise

    async def stream(
            self,
            prompt: str,
            history: List[ChatTurn] | None = None,
            system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        messages: list[BaseMessage] = self._build_messages(prompt, history, system_prompt=system_prompt)

        for _turn in range(self._max_turns):
            accumulated: Any = None
            async for chunk in self._bound_model.astream(messages):
                try:
                    chunk_content = chunk.content
                except AttributeError:
                    chunk_content = None
                if chunk_content:
                    yield str(chunk_content)
                accumulated = chunk if accumulated is None else accumulated + chunk

            try:
                tool_calls = accumulated.tool_calls
            except AttributeError:
                tool_calls = None

            if tool_calls:
                messages.append(accumulated)
                await asyncio.to_thread(self._execute_tool_calls, tool_calls, messages)
                continue
            break
