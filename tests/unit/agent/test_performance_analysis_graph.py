from __future__ import annotations

from unittest.mock import Mock

from src.agent.gateway import AgentGateway
from src.agent.performance_analysis.graph import PerformanceAnalysisGraph
from src.agent.performance_analysis.models import MetricQueryIntent
from src.agent.performance_analysis.nodes.analyze_metrics import AnalyzeMetricsNode
from src.agent.performance_analysis.nodes.fetch_metrics import FetchMetricsNode
from src.agent.performance_analysis.nodes.present_analysis import PresentAnalysisNode
from src.agent.performance_analysis.nodes.understand_query import UnderstandMetricQueryNode
from src.agent.router.models import AgentGoal, AgentIntent, AgentRoute
from src.core.interfaces.llm_adapter import ChatTurn
from tests.unit.agent.fakes import FakeLlmAdapter


class TestUnderstandMetricQueryNode:
    def test_parses_query_intent_with_history(self):
        expected_intent = MetricQueryIntent(
            metric_names=["orders.executed"],
            lookback_seconds=300,
            analysis_focus="throughput",
        )
        llm = FakeLlmAdapter([expected_intent])
        node = UnderstandMetricQueryNode(llm)

        state = {
            "user_prompt": "How many orders were executed in the last 5 minutes?",
            "history": [ChatTurn(role="user", content="Hello")],
        }
        out = node(state)

        assert out["query_intent"] == expected_intent
        assert llm.structured_calls[0][0] is MetricQueryIntent
        prompt = llm.structured_calls[0][1]
        assert "How many orders were executed in the last 5 minutes?" in prompt
        assert "Hello" in prompt


class TestFetchMetricsNode:
    def test_fetches_metrics_from_registered_tool(self):
        tool = Mock()
        tool.name = "query_metrics"
        tool.invoke.return_value = "Metric: orders.executed sum=10"
        llm = FakeLlmAdapter(tools=[tool])

        node = FetchMetricsNode(llm)
        intent = MetricQueryIntent(metric_names=["orders.executed"], lookback_seconds=300)
        out = node({"query_intent": intent})

        assert "Metric: orders.executed sum=10" in out["metric_data"]
        tool.invoke.assert_called_once_with({
            "metric_names": ["orders.executed"],
            "lookback_seconds": 300,
            "interval_seconds": 60,
            "aggregation": None,
            "labels": None,
        })


    def test_returns_fallback_when_tool_missing(self):
        llm = FakeLlmAdapter()
        node = FetchMetricsNode(llm)
        out = node({"query_intent": MetricQueryIntent()})

        assert "Metrics tool is not available" in out["metric_data"]


class TestAnalyzeMetricsNode:
    def test_generates_analysis_from_metric_data(self):
        llm = FakeLlmAdapter(text="Order throughput averaged 2 orders/min.")
        node = AnalyzeMetricsNode(llm)

        out = node({
            "user_prompt": "Analyze order execution rate",
            "query_intent": MetricQueryIntent(analysis_focus="throughput"),
            "metric_data": "Metric: orders.executed sum=10",
        })

        assert out["analysis_summary"] == "Order throughput averaged 2 orders/min."


class TestPresentAnalysisNode:
    def test_presents_analysis_summary_as_markdown_block(self):
        node = PresentAnalysisNode()
        out = node({"analysis_summary": "Healthy throughput."})

        assert len(out["presentation"].blocks) == 1
        assert out["presentation"].blocks[0].content == "Healthy throughput."


class TestPerformanceAnalysisGraph:
    def test_runs_end_to_end(self):
        query_intent = MetricQueryIntent(
            metric_names=["orders.submitted"],
            lookback_seconds=3600,
            analysis_focus="orders",
        )
        tool = Mock()
        tool.name = "query_metrics"
        tool.invoke.return_value = "Metric: orders.submitted sum=42"
        llm = FakeLlmAdapter(

            structured_results=[query_intent],
            text="Analysis: 42 orders were submitted over the past hour.",
            tools=[tool],
        )

        graph = PerformanceAnalysisGraph(llm).build()
        state = graph.invoke({
            "user_prompt": "How many orders were submitted in the last hour?",
            "request": AgentRoute(
                intent=AgentIntent.PERFORMANCE_ANALYSIS,
                goal=AgentGoal(objective="check submitted orders"),
            ),
        })

        assert state["query_intent"] == query_intent
        assert "Metric: orders.submitted sum=42" in state["metric_data"]
        assert "42 orders were submitted" in state["analysis_summary"]
        assert "42 orders were submitted" in state["presentation"].blocks[0].content


class TestPerformanceAnalysisAgentRegistration:
    def test_registered_with_graph_in_default_registry(self, sample_config):
        registry = AgentGateway.build_default_registry(FakeLlmAdapter(), sample_config)
        definition = registry.get(AgentIntent.PERFORMANCE_ANALYSIS)
        assert definition.name == "performance_analysis"
        assert definition.graph is not None
        assert definition.presentation_node == "present_analysis"
        assert registry.agent_name_for(AgentIntent.PERFORMANCE_ANALYSIS) == "performance_analysis"
