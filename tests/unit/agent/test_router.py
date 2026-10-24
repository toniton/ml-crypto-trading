from unittest.mock import MagicMock
from datetime import datetime, timezone

from src.agent.operational.models import (
    OperationalConditionSummary,
    OperationalContext,
    OperationalReadinessStatus,
)
from src.agent.router.graph import RouterGraph
from src.agent.router.models import AgentGoal, AgentIntent, AgentRoute
from src.agent.router.nodes.operational_status import OperationalStatusNode
from src.agent import RouteNode
from src.agent import UnderstandGoalNode
from src.core.interfaces.llm_adapter import ChatTurn
from tests.unit.agent.fakes import FakeLlmAdapter


class TestOperationalStatusNode:
    def test_node_collects_context_and_populates_state(self):
        collector = MagicMock()
        expected_context = OperationalContext.unavailable("testing")
        collector.collect.return_value = expected_context

        node = OperationalStatusNode(collector)
        result = node({"user_prompt": "hello"})

        assert result["operational_context"] == expected_context


class TestUnderstandGoalNode:
    def test_invokes_structured_route(self, sample_config):
        llm = FakeLlmAdapter([
            AgentRoute(
                intent=AgentIntent.CONFIGURATION,
                goal=AgentGoal(objective="Take more trades"),
            ),
        ])
        node = UnderstandGoalNode(llm)
        result = node({"user_prompt": "I want more trades"})
        assert result["route"].intent == AgentIntent.CONFIGURATION
        assert result["route"].goal.objective == "Take more trades"
        assert llm.structured_calls[0][0] is AgentRoute

    def test_includes_conversation_history_in_prompt(self):
        llm = FakeLlmAdapter([
            AgentRoute(intent=AgentIntent.BACKTEST),
        ])
        node = UnderstandGoalNode(llm)
        history = [
            ChatTurn(role="user", content="Run a backtest for DOGE_USD over the last 1 minute."),
            ChatTurn(role="assistant", content="Please provide the execution costs."),
        ]
        node({"user_prompt": "fee rate: 0.0001, slippage: 3, latency 700ms", "history": history})
        prompt = llm.structured_calls[0][1]
        assert "Run a backtest for DOGE_USD" in prompt
        assert "fee rate: 0.0001, slippage: 3, latency 700ms" in prompt


class TestRouteNode:
    def test_resolves_intent_via_callback(self):
        def resolve(intent: AgentIntent) -> str:
            return "configuration" if intent is AgentIntent.CONFIGURATION else "general"

        node = RouteNode(resolve)
        result = node({"user_prompt": "x", "route": AgentRoute(intent=AgentIntent.CONFIGURATION)})
        assert result["agent"] == "configuration"

    def test_unknown_intent_falls_back_to_general(self):
        node = RouteNode(lambda _intent: "general")
        result = node({"user_prompt": "x", "route": AgentRoute(intent=AgentIntent.GENERAL)})
        assert result["agent"] == "general"


class TestRouterGraph:
    def test_route_produces_typed_route(self, sample_config):
        llm = FakeLlmAdapter([
            AgentRoute(
                intent=AgentIntent.RISK_ANALYSIS,
                goal=AgentGoal(objective="check drawdown"),
            ),
        ])
        graph = RouterGraph(llm).build()
        state = graph.invoke({"user_prompt": "check drawdown"})

        assert state["route"].intent == AgentIntent.RISK_ANALYSIS
        assert state["route"].goal.objective == "check drawdown"
        # default resolver uses the intent value as the agent name
        assert state["agent"] == AgentIntent.RISK_ANALYSIS.value
        assert len(llm.structured_calls) == 1

    def test_clarification_route(self, sample_config):
        llm = FakeLlmAdapter([
            AgentRoute(
                intent=AgentIntent.CONFIGURATION,
                requires_clarification=True,
                clarification_question="What would you like to improve: profitability, trade frequency, or drawdown?",
            ),
        ])
        graph = RouterGraph(llm).build()
        state = graph.invoke({"user_prompt": "make it better"})
        route = state["route"]
        assert route.requires_clarification is True
        assert "profitability" in route.clarification_question

    def test_decision_investigation_routing_with_commit_hash(self, sample_config):
        llm = FakeLlmAdapter([
            # Even if LLM returns CONFIGURATION, deterministic enrichment should promote to DECISION_INVESTIGATION
            AgentRoute(
                intent=AgentIntent.CONFIGURATION,
                goal=AgentGoal(objective="Ask about proposal"),
            ),
        ])
        graph = RouterGraph(llm).build()
        state = graph.invoke({"user_prompt": "Why are you proposing these changes for CRO_USD (Base: 235f666)?"})
        route = state["route"]
        assert route.intent == AgentIntent.DECISION_INVESTIGATION
        assert route.references is not None
        assert route.references.asset == "CRO_USD"
        assert route.references.commit_hash == "235f666"

    def test_explain_commit_query_routes_to_decision_investigation(self):
        llm = FakeLlmAdapter([
            AgentRoute(intent=AgentIntent.GENERAL),
        ])
        node = UnderstandGoalNode(llm)
        result = node({"user_prompt": "Explain commit 235f666"})
        route = result["route"]
        assert route.intent == AgentIntent.DECISION_INVESTIGATION
        assert route.references.commit_hash == "235f666"

    def test_paused_bot_routes_inactivity_query_to_runtime_debug(self):
        llm = FakeLlmAdapter([
            AgentRoute(intent=AgentIntent.GENERAL),
        ])
        paused_context = OperationalContext(
            status=OperationalReadinessStatus.PAUSED,
            health_state="PAUSED",
            is_trading_allowed=False,
            active_conditions=(),
            effective_permissions=(),
            observed_at=datetime.now(timezone.utc),
            snapshot_version=1,
            is_available=True,
        )
        collector = MagicMock()
        collector.collect.return_value = paused_context

        graph = RouterGraph(llm, collector=collector).build()
        state = graph.invoke({"user_prompt": "Why hasn't BTC traded today?"})

        assert state["route"].intent == AgentIntent.RUNTIME_DEBUG

    def test_healthy_bot_routes_inactivity_query_to_decision_investigation(self):
        llm = FakeLlmAdapter([
            AgentRoute(intent=AgentIntent.DECISION_INVESTIGATION),
        ])
        healthy_context = OperationalContext(
            status=OperationalReadinessStatus.READY,
            health_state="TRADING",
            is_trading_allowed=True,
            active_conditions=(),
            effective_permissions=("new_orders",),
            observed_at=datetime.now(timezone.utc),
            snapshot_version=1,
            is_available=True,
        )
        collector = MagicMock()
        collector.collect.return_value = healthy_context

        graph = RouterGraph(llm, collector=collector).build()
        state = graph.invoke({"user_prompt": "Why hasn't BTC traded today?"})

        assert state["route"].intent == AgentIntent.DECISION_INVESTIGATION

    def test_degraded_bot_preserves_configuration_view_intent(self):
        llm = FakeLlmAdapter([
            AgentRoute(intent=AgentIntent.CONFIGURATION),
        ])
        degraded_context = OperationalContext(
            status=OperationalReadinessStatus.DEGRADED,
            health_state="DEGRADED",
            is_trading_allowed=False,
            active_conditions=(),
            effective_permissions=(),
            observed_at=datetime.now(timezone.utc),
            snapshot_version=1,
            is_available=True,
        )
        collector = MagicMock()
        collector.collect.return_value = degraded_context

        graph = RouterGraph(llm, collector=collector).build()
        state = graph.invoke({"user_prompt": "Show current BTC configuration"})

        assert state["route"].intent == AgentIntent.CONFIGURATION

    def test_router_includes_operational_context_in_prompt(self):
        llm = FakeLlmAdapter([
            AgentRoute(intent=AgentIntent.GENERAL),
        ])
        active_cond = OperationalConditionSummary(
            condition="order_rejection_spike",
            scope_type="exchange",
            scope_identifier="BINANCE",
            severity="critical",
            first_detected_at=datetime.now(timezone.utc),
            last_observed_at=datetime.now(timezone.utc),
        )
        paused_context = OperationalContext(
            status=OperationalReadinessStatus.PAUSED,
            health_state="PAUSED",
            is_trading_allowed=False,
            active_conditions=(active_cond,),
            effective_permissions=("cancel_orders",),
            observed_at=datetime.now(timezone.utc),
            snapshot_version=2,
            is_available=True,
        )
        collector = MagicMock()
        collector.collect.return_value = paused_context

        graph = RouterGraph(llm, collector=collector).build()
        graph.invoke({"user_prompt": "Are orders failing?"})

        prompt = llm.structured_calls[0][1]
        assert "OPERATIONAL CONTEXT" in prompt
        assert "status = paused" in prompt
        assert "order_rejection_spike" in prompt
