import asyncio

from src.agent import AgentGateway
from src.agent import (
    ConfigChange,
    ConfigurationProposal,
)
from src.agent.router.models import AgentGoal, AgentIntent, AgentRoute, ConfigurationAction
from src.core.interfaces.llm_adapter import ChatTurn
from tests.unit.agent.fakes import FakeLlmAdapter


class TestAgentGateway:
    def _config_route(self, objective="take more trades"):
        return AgentRoute(
            intent=AgentIntent.CONFIGURATION,
            goal=AgentGoal(objective=objective),
        )

    def _clarification_route(self):
        return AgentRoute(
            intent=AgentIntent.CONFIGURATION,
            goal=AgentGoal(objective="make it better"),
            requires_clarification=True,
            clarification_question="What would you like to improve: profitability, trade frequency, or drawdown?",
        )

    def test_general_prompt_routed_by_intent(self, sample_config):
        llm = FakeLlmAdapter([AgentRoute(intent=AgentIntent.GENERAL)])
        gateway = AgentGateway(llm, sample_config)
        result = gateway.handle("Analyze the market")
        assert result.kind == "general"
        assert len(llm.structured_calls) == 1

    def test_analysis_intent_falls_back_to_general_without_a_graph(self, sample_config):
        llm = FakeLlmAdapter([AgentRoute(intent=AgentIntent.PERFORMANCE_ANALYSIS)])
        gateway = AgentGateway(llm, sample_config)
        result = gateway.handle("Why did BTC strategy perform badly last week?")
        assert result.kind == "general"

    def test_configuration_prompt_runs_graph(self, sample_config):
        llm = FakeLlmAdapter([
            self._config_route(),
            ConfigurationProposal(
                summary="less conservative",
                changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1, reason="more trades")],
            ),
        ])
        gateway = AgentGateway(llm, sample_config)
        result = gateway.handle("make the strategy less conservative")
        assert result.kind == "configuration"
        assert result.proposal is not None
        assert result.proposal.summary == "less conservative"
        assert "assets.BTC_USD.consensus.buy: 1.3 -> 1.1" in result.presentation.markdown()
        # one routing call in the router graph, one proposal call in the graph
        assert len(llm.structured_calls) == 2

    def test_semantic_config_detection_without_typical_keywords(self, sample_config):
        llm = FakeLlmAdapter([
            self._config_route(objective="aggressive position sizing"),
            ConfigurationProposal(
                summary="riskier sizing",
                changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.05, reason="riskier")],
            ),
        ])
        gateway = AgentGateway(llm, sample_config)
        result = gateway.handle("I'd like my bot to be a bit riskier on sizing")
        assert result.kind == "configuration"
        assert result.proposal is not None

    def test_dynamic_quantity_intent_runs_graph(self, sample_config):
        llm = FakeLlmAdapter([
            self._config_route(objective="update dynamic quantity"),
            ConfigurationProposal(
                summary="update dynamic quantity",
                changes=[
                    ConfigChange(
                        path="dynamic_quantity",
                        old_value="old formula",
                        new_value="new formula",
                        reason="adjust risk management",
                    )
                ],
            ),
        ])
        gateway = AgentGateway(llm, sample_config)
        result = gateway.handle("Update dynamic quantity in my configuration.")
        assert result.kind == "configuration"
        assert result.proposal.changes[0].path == "dynamic_quantity"

    def test_clarification_prompt_short_circuits_handle(self, sample_config):
        llm = FakeLlmAdapter([self._clarification_route()])
        gateway = AgentGateway(llm, sample_config)
        result = gateway.handle("make it better")
        assert result.kind == "clarification"
        assert "profitability" in result.question
        assert result.intent == AgentIntent.CONFIGURATION
        assert result.goal.objective == "make it better"
        # only the router ran; no agent graph was invoked
        assert len(llm.structured_calls) == 1

    def test_clarification_prompt_short_circuits_stream(self, sample_config):
        llm = FakeLlmAdapter([self._clarification_route()])
        gateway = AgentGateway(llm, sample_config)

        async def collect():
            return [event async for event in gateway.stream("make it better")]

        events = asyncio.run(collect())
        types = [event.type for event in events]
        assert "clarification" in types
        assert types[-1] == "done"
        assert "token" not in types
        clarification = next(event for event in events if event.type == "clarification")
        assert "profitability" in clarification.payload["question"]
        assert clarification.payload["intent"] == "configuration"
        assert clarification.payload["goal"].objective == "make it better"
        assert events[-1].payload == {"kind": "clarification"}

    def test_general_stream_forwards_history(self, sample_config):
        llm = FakeLlmAdapter([AgentRoute(intent=AgentIntent.GENERAL)], chunks=["a", "b"])
        gateway = AgentGateway(llm, sample_config)
        history = [ChatTurn(role="user", content="what is BTC?"), ChatTurn(role="assistant", content="It is Bitcoin.")]

        async def collect():
            return [event async for event in gateway.stream("and ETH?", history=history)]

        events = asyncio.run(collect())
        assert events[-1].type == "done"
        assert llm.last_history == history

    def test_configuration_prompt_includes_history(self, sample_config):
        history = [ChatTurn(role="user", content="make the strategy less conservative")]
        llm = FakeLlmAdapter([
            self._config_route(),
            ConfigurationProposal(
                summary="less conservative",
                changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1, reason="more trades")],
            ),
        ])
        gateway = AgentGateway(llm, sample_config)
        result = gateway.handle("make it a bit more aggressive", history=history)
        assert result.kind == "configuration"
        proposal_prompt = llm.structured_calls[1][1]
        assert "CONVERSATION HISTORY" in proposal_prompt
        assert "make the strategy less conservative" in proposal_prompt

    def test_view_configuration_prompt_skips_proposal(self, sample_config):
        llm = FakeLlmAdapter([
            AgentRoute(
                intent=AgentIntent.CONFIGURATION,
                action=ConfigurationAction.VIEW,
                goal=AgentGoal(objective="show BTC_USD config", target_asset="BTC_USD"),
            ),
        ])
        gateway = AgentGateway(llm, sample_config)
        result = gateway.handle("show me configuration for BTC_USD")
        assert result.kind == "configuration"
        assert result.proposal is None
        assert result.validation is None
        assert result.presentation is not None
        assert "assets.BTC_USD.consensus.buy" in result.presentation.markdown()
        assert any(block.type == "configuration_view" for block in result.presentation.blocks)
        # only the router ran; no proposal LLM call was made
        assert len(llm.structured_calls) == 1
