from src.agent.router.graph import RouterGraph
from src.agent.router.models import AgentGoal, AgentIntent, AgentRoute
from src.agent import RouteNode
from src.agent import UnderstandGoalNode
from src.core.interfaces.llm_adapter import ChatTurn
from tests.unit.agent.fakes import FakeLlmAdapter


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