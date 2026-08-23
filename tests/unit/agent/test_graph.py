from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.configuration.graph import MAX_GENERATION_ATTEMPTS, ConfigurationGraph
from src.agent import (
    ConfigChange,
    ConfigurationProposal,
    ValidationResult,
)
from src.agent.router.models import AgentGoal, AgentIntent, AgentRoute, ConfigurationAction
from tests.unit.agent.fakes import FakeLlmAdapter


class TestRouteAfterValidation:
    def test_valid_routes_to_present(self):
        assert ConfigurationGraph.route_after_validation({
            "validation": ValidationResult.ok(),
            "proposal_attempts": 1,
        }) == "present"

    def test_invalid_with_attempts_left_routes_to_regenerate(self):
        assert ConfigurationGraph.route_after_validation({
            "validation": ValidationResult.failed(["boom"]),
            "proposal_attempts": 1,
        }) == "regenerate"

    def test_invalid_after_max_attempts_routes_to_present(self):
        assert ConfigurationGraph.route_after_validation({
            "validation": ValidationResult.failed(["boom"]),
            "proposal_attempts": MAX_GENERATION_ATTEMPTS,
        }) == "present"


class TestRouteByAction:
    def test_view_action_routes_to_view(self):
        route = AgentRoute(intent=AgentIntent.CONFIGURATION, action=ConfigurationAction.VIEW)
        assert ConfigurationGraph.route_by_action({"request": route}) == "view"

    def test_modify_action_routes_to_modify(self):
        route = AgentRoute(intent=AgentIntent.CONFIGURATION, action=ConfigurationAction.MODIFY)
        assert ConfigurationGraph.route_by_action({"request": route}) == "modify"

    def test_missing_request_defaults_to_modify(self):
        assert ConfigurationGraph.route_by_action({}) == "modify"


class TestConfigurationGraph:
    def _config_route(self, objective="take more trades", target_asset=None):
        return AgentRoute(
            intent=AgentIntent.CONFIGURATION,
            goal=AgentGoal(objective=objective, target_asset=target_asset),
        )

    def test_preloaded_request_never_requires_understanding(self, sample_config):
        """The router owns understanding: the graph starts from the request."""
        llm = FakeLlmAdapter([
            ConfigurationProposal(
                summary="less conservative",
                changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1, reason="r")],
            ),
        ])
        graph = ConfigurationGraph(llm, ConfigurationService(sample_config)).build()
        state = graph.invoke({
            "user_prompt": "x",
            "request": self._config_route(),
        })
        assert state["validation"].valid is True
        assert len(llm.structured_calls) == 1
        assert llm.structured_calls[0][0] is ConfigurationProposal

    def test_view_request_presents_config_without_proposal(self, sample_config):
        llm = FakeLlmAdapter([])
        graph = ConfigurationGraph(llm, ConfigurationService(sample_config)).build()
        route = AgentRoute(
            intent=AgentIntent.CONFIGURATION,
            action=ConfigurationAction.VIEW,
            goal=AgentGoal(objective="show BTC_USD config", target_asset="BTC_USD"),
        )
        state = graph.invoke({"user_prompt": "show me configuration for BTC_USD", "request": route})

        assert "proposal" not in state
        assert "validation" not in state
        assert not llm.structured_calls
        blocks = state["presentation"].blocks
        assert len(blocks) == 1
        assert blocks[0].type == "configuration_view"
        view = blocks[0]
        assert view.asset == "BTC_USD"
        assert view.base == "BTC" and view.quote == "USD"
        assert "dynamic_quantity" not in [field.path for section in view.sections for field in section.fields]
        consensus = next(section for section in view.sections if section.title == "Consensus thresholds")
        field_paths = [field.path for field in consensus.fields]
        assert "assets.BTC_USD.consensus.buy" in field_paths
        assert view.signal_window is not None
        assert any(card.label == "Strategies" for card in view.stats)
        assert view.signal_window.sell == 0.5 and view.signal_window.buy == 1.3

    def test_view_request_without_asset_renders_full_catalog(self, sample_config):
        llm = FakeLlmAdapter([])
        graph = ConfigurationGraph(llm, ConfigurationService(sample_config)).build()
        route = AgentRoute(
            intent=AgentIntent.CONFIGURATION,
            action=ConfigurationAction.VIEW,
            goal=AgentGoal(objective="show config"),
        )
        state = graph.invoke({"user_prompt": "show me my configuration", "request": route})

        blocks = state["presentation"].blocks
        assert blocks[0].type == "markdown"
        assert "dynamic_quantity" in blocks[0].content

    def test_scoped_request_presentation_warns_about_global_field(self, sample_config):
        llm = FakeLlmAdapter([
            ConfigurationProposal(
                summary="more aggressive",
                changes=[
                    ConfigChange(
                        path="dynamic_quantity",
                        old_value="old formula",
                        new_value="aggro formula",
                        reason="more aggressive",
                    ),
                ],
            ),
        ])
        graph = ConfigurationGraph(llm, ConfigurationService(sample_config)).build()
        state = graph.invoke({
            "user_prompt": "make dynamic quantity more aggressive for BTC_USD",
            "request": self._config_route(objective="more aggressive sizing", target_asset="BTC_USD"),
        })
        assert state["validation"].valid is True
        assert "global" in state["presentation"].markdown()

    def test_valid_proposal_ends_with_presentation(self, sample_config):
        route = AgentRoute(
            intent=AgentIntent.CONFIGURATION,
            goal=AgentGoal(objective="take more trades", desired_outcomes=["more signals"]),
        )
        llm = FakeLlmAdapter([
            ConfigurationProposal(
                summary="less conservative",
                changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1, reason="more signals")],
                expected_effect="more buy signals",
            ),
        ])
        graph = ConfigurationGraph(llm, ConfigurationService(sample_config)).build()
        state = graph.invoke({"user_prompt": "make the strategy less conservative", "request": route})

        assert state["request"].goal.objective == "take more trades"
        assert state["validation"].valid is True
        assert state["proposal"].changes[0].path == "assets.BTC_USD.consensus.buy"
        assert "assets.BTC_USD.consensus.buy: 1.3 -> 1.1" in state["presentation"].markdown()

    def test_invalid_then_regenerated_proposal(self, sample_config):
        llm = FakeLlmAdapter([
            ConfigurationProposal(
                summary="broken",
                changes=[ConfigChange(path="bogus.path", old_value=None, new_value=1, reason="x")],
            ),
            ConfigurationProposal(
                summary="fixed",
                changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1, reason="fixed")],
            ),
        ])
        graph = ConfigurationGraph(llm, ConfigurationService(sample_config)).build()
        state = graph.invoke({
            "user_prompt": "take more trades",
            "request": self._config_route(),
        })

        assert state["validation"].valid is True
        assert state["proposal"].summary == "fixed"
        regeneration_prompt = llm.structured_calls[1][1]
        assert "broken" in regeneration_prompt
        assert "bogus.path" in regeneration_prompt

    def test_persistently_invalid_proposal_stops_after_max_attempts(self, sample_config):
        invalid = ConfigurationProposal(
            summary="always broken",
            changes=[ConfigChange(path="bogus.path", old_value=None, new_value=1, reason="x")],
        )
        llm = FakeLlmAdapter([invalid, invalid, invalid])
        graph = ConfigurationGraph(llm, ConfigurationService(sample_config)).build()
        state = graph.invoke({
            "user_prompt": "change something",
            "request": self._config_route(),
        })

        assert state["validation"].valid is False
        assert state["validation"].errors
        assert llm.structured_calls[1][0] is ConfigurationProposal
        assert not any(block.type == "approval" for block in state["presentation"].blocks)
        assert "rejected" in state["presentation"].markdown()
