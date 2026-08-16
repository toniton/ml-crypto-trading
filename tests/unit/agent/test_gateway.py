from src.agent import AgentGateway
from src.agent import (
    ConfigChange,
    ConfigurationProposal,
)
from src.agent.router.models import AgentGoal, AgentIntent, AgentRoute
from tests.unit.agent.fakes import FakeLlmAdapter


class TestAgentGateway:
    def _config_route(self, objective="take more trades"):
        return AgentRoute(
            intent=AgentIntent.CONFIGURATION,
            goal=AgentGoal(objective=objective),
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
                changes=[ConfigChange(path="consensus.buy", old_value=1.3, new_value=1.1, reason="more trades")],
            ),
        ])
        gateway = AgentGateway(llm, sample_config)
        result = gateway.handle("make the strategy less conservative")
        assert result.kind == "configuration"
        assert result.proposal is not None
        assert result.proposal.summary == "less conservative"
        assert "consensus.buy: 1.3 -> 1.1" in result.presentation.markdown()
        # one routing call in the router graph, one proposal call in the graph
        assert len(llm.structured_calls) == 2

    def test_semantic_config_detection_without_typical_keywords(self, sample_config):
        llm = FakeLlmAdapter([
            self._config_route(objective="aggressive position sizing"),
            ConfigurationProposal(
                summary="riskier sizing",
                changes=[ConfigChange(path="consensus.buy", old_value=1.3, new_value=1.05, reason="riskier")],
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