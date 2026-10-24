from __future__ import annotations

from unittest.mock import MagicMock

from src.agent.runtime.system_context import (
    collect_machine_snapshot,
    collect_workflow_runtime_context,
    format_machine_snapshot,
)
from src.agent.runtime_debug.nodes.load_context_node import LoadContextNode
from src.agent.runtime_debug.tools import RuntimeDebugToolbox
from src.core.interfaces.llm_adapter import LlmAdapter
from src.llm.dynamic_llm_adapter import DynamicLlmAdapter


def test_collect_and_format_machine_snapshot():
    snap = collect_machine_snapshot()
    formatted = format_machine_snapshot(snap)
    assert "Machine & Process Runtime Context:" in formatted
    assert str(snap["pid"]) in formatted


def test_collect_workflow_runtime_context_includes_machine_and_health():
    llm = MagicMock(spec=LlmAdapter)
    health_tool = MagicMock()
    health_tool.invoke.return_value = "Global State: HEALTHY"
    llm.get_tool.side_effect = lambda name: health_tool if name == "trading_health" else None

    ctx = collect_workflow_runtime_context(llm, include_session=False)
    assert "Machine & Process Runtime Context:" in ctx
    assert "Global State: HEALTHY" in ctx


def test_load_context_node_populates_machine_snapshot():
    toolbox = RuntimeDebugToolbox()
    node = LoadContextNode(toolbox)
    out = node({})
    assert "machine" in out["context"]
    assert "pid" in out["context"]["machine"]


def test_dynamic_llm_adapter_fails_over_on_402_insufficient_balance():
    primary = MagicMock(spec=LlmAdapter)
    primary.generate.side_effect = ValueError(
        "Error code: 402 - {'error': {'message': 'Insufficient Balance'}}"
    )
    fallback = MagicMock(spec=LlmAdapter)
    fallback.generate.return_value = "Recovered response from fallback model"

    manager = MagicMock()
    manager.get_active_adapter.return_value = primary
    manager.try_failover_adapter.return_value = fallback

    proxy = DynamicLlmAdapter(manager)
    response = proxy.generate("What are my balances?")
    assert response == "Recovered response from fallback model"
