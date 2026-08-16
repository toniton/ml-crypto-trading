import pytest

from src.agent import AgentGateway
from src.agent.router.models import AgentIntent
from src.agent.runtime import AgentDefinition
from src.agent.runtime import AgentRegistry
from tests.unit.agent.fakes import FakeLlmAdapter


class TestAgentRegistry:
    def test_resolves_registered_intent(self):
        registry = AgentRegistry([AgentDefinition(name="configuration", description="cfg")])
        registry.register(AgentIntent.CONFIGURATION, "configuration")
        assert registry.get(AgentIntent.CONFIGURATION).name == "configuration"

    def test_unknown_intent_falls_back_to_general(self):
        general = AgentDefinition(name="general", description="g")
        registry = AgentRegistry([general])
        registry.register(AgentIntent.GENERAL, "general")
        assert registry.get(AgentIntent.RISK_ANALYSIS) is general
        assert registry.agent_name_for(AgentIntent.RISK_ANALYSIS) == "general"

    def test_register_unknown_agent_raises(self):
        registry = AgentRegistry([AgentDefinition(name="general", description="g")])
        with pytest.raises(KeyError):
            registry.register(AgentIntent.GENERAL, "does-not-exist")


class TestDefaultRegistry:
    def test_configuration_agent_has_graph(self, sample_config):
        registry = AgentGateway.build_default_registry(FakeLlmAdapter(), sample_config)
        definition = registry.get(AgentIntent.CONFIGURATION)
        assert definition.name == "configuration"
        assert definition.graph is not None
        assert definition.presentation_node == "present_proposal"

    def test_specialized_agents_registered_as_stubs(self, sample_config):
        registry = AgentGateway.build_default_registry(FakeLlmAdapter(), sample_config)
        for intent in (
            AgentIntent.PERFORMANCE_ANALYSIS,
            AgentIntent.RISK_ANALYSIS,
            AgentIntent.MARKET_ANALYSIS,
            AgentIntent.REPORTING,
            AgentIntent.SYSTEM_HELP,
        ):
            definition = registry.get(intent)
            assert definition.graph is None
            assert definition.name == intent.value

    def test_general_agent_registered(self, sample_config):
        registry = AgentGateway.build_default_registry(FakeLlmAdapter(), sample_config)
        assert registry.get(AgentIntent.GENERAL).name == "general"

    def test_intents_are_decoupled_from_agent_names(self, sample_config):
        registry = AgentGateway.build_default_registry(FakeLlmAdapter(), sample_config)
        agent = AgentDefinition(name="configuration", description="cfg")
        registry.register(AgentIntent.CONFIGURATION, "configuration")
        # intent value and agent name both "configuration" today, but the mapping
        # is explicit, not derived from the enum value.
        assert registry.agent_name_for(AgentIntent.CONFIGURATION) == agent.name