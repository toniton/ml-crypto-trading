from src.agent.configuration.configuration_service import ConfigurationService
from src.agent import (
    ConfigChange,
    ConfigurationProposal,
    ValidationResult,
)
from src.agent import GenerateProposalNode
from src.agent.configuration.nodes.load_configuration import LoadConfigurationNode
from src.agent import PresentProposalNode
from src.agent import ValidateProposalNode
from src.agent.router.models import AgentGoal, AgentIntent, AgentRoute
from tests.unit.agent.fakes import FakeLlmAdapter


class TestLoadConfigurationNode:
    def test_renders_catalog(self, sample_config):
        node = LoadConfigurationNode(ConfigurationService(sample_config))
        result = node({"user_prompt": "x"})
        assert "assets.BTC_USD.consensus.buy" in result["catalog_context"]


class TestGenerateProposalNode:
    def _route(self, objective="take more trades", target_asset=None):
        return AgentRoute(
            intent=AgentIntent.CONFIGURATION,
            goal=AgentGoal(objective=objective, target_asset=target_asset),
        )

    def test_first_generation_uses_goal_and_catalog(self, sample_config):
        llm = FakeLlmAdapter([ConfigurationProposal(summary="s", changes=[])])
        node = GenerateProposalNode(llm, ConfigurationService(sample_config))
        result = node({
            "user_prompt": "x",
            "request": self._route(),
            "catalog_context": "assets.BTC_USD.consensus.buy [editable, decimal] = 1.3",
            "proposal_attempts": 0,
        })
        assert result["proposal"].summary == "s"
        assert result["proposal_attempts"] == 1
        prompt = llm.structured_calls[0][1]
        assert "assets.BTC_USD.consensus.buy" in prompt
        assert "take more trades" in prompt

    def test_goal_format_includes_target_asset(self, sample_config):
        llm = FakeLlmAdapter([ConfigurationProposal(summary="s", changes=[])])
        node = GenerateProposalNode(llm, ConfigurationService(sample_config))
        node({
            "user_prompt": "x",
            "request": self._route(objective="more aggressive sizing", target_asset="BTC_USD"),
            "catalog_context": "catalog",
            "proposal_attempts": 0,
        })
        prompt = llm.structured_calls[0][1]
        assert "Target asset: BTC_USD" in prompt

    def test_regeneration_includes_previous_proposal_and_full_validation(self, sample_config):
        llm = FakeLlmAdapter([ConfigurationProposal(summary="fixed", changes=[])])
        node = GenerateProposalNode(llm, ConfigurationService(sample_config))
        result = node({
            "user_prompt": "x",
            "request": self._route(),
            "catalog_context": "catalog",
            "proposal": ConfigurationProposal(summary="broken", changes=[]),
            "validation": ValidationResult(
                valid=False,
                errors=["Field 'nope' violates constraint"],
                warnings=["global setting applies to all assets"],
            ),
            "proposal_attempts": 1,
        })
        prompt = llm.structured_calls[0][1]
        assert "broken" in prompt
        assert "Field 'nope' violates constraint" in prompt
        assert "global setting applies to all assets" in prompt


class TestValidateProposalNode:
    def _route(self, objective="take more trades", target_asset=None):
        return AgentRoute(
            intent=AgentIntent.CONFIGURATION,
            goal=AgentGoal(objective=objective, target_asset=target_asset),
        )

    def test_valid_proposal_passes(self, sample_config):
        node = ValidateProposalNode(ConfigurationService(sample_config))
        proposal = ConfigurationProposal(
            summary="s",
            changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1, reason="r")],
        )
        result = node({"proposal": proposal, "request": self._route()})
        assert result["validation"].valid is True

    def test_invalid_proposal_reports_errors(self, sample_config):
        node = ValidateProposalNode(ConfigurationService(sample_config))
        proposal = ConfigurationProposal(
            summary="s",
            changes=[ConfigChange(path="bogus.path", old_value=None, new_value=1, reason="r")],
        )
        result = node({"proposal": proposal, "request": self._route()})
        assert result["validation"].valid is False
        assert result["validation"].errors

    def test_scoped_request_warns_on_global_change(self, sample_config):
        node = ValidateProposalNode(ConfigurationService(sample_config))
        proposal = ConfigurationProposal(
            summary="aggro",
            changes=[
                ConfigChange(path="dynamic_quantity", old_value="old", new_value="new", reason="aggro"),
            ],
        )
        result = node({"proposal": proposal, "request": self._route(target_asset="BTC_USD")})
        assert any("global" in warning for warning in result["validation"].warnings)

    def test_scoped_request_no_warning_on_asset_path(self, sample_config):
        node = ValidateProposalNode(ConfigurationService(sample_config))
        proposal = ConfigurationProposal(
            summary="cadence",
            changes=[ConfigChange(path="assets.BTC_USD.schedule", old_value=1, new_value=2, reason="faster")],
        )
        result = node({"proposal": proposal, "request": self._route(target_asset="BTC_USD")})
        assert result["validation"].warnings == []


class TestPresentProposalNode:
    def test_renders_structured_presentation(self, sample_config):
        node = PresentProposalNode(ConfigurationService(sample_config))
        proposal = ConfigurationProposal(
            summary="less conservative",
            changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1, reason="more trades")],
        )
        result = node({"proposal": proposal})
        presentation = result["presentation"]
        assert "less conservative" in presentation.markdown()
        assert "assets.BTC_USD.consensus.buy: 1.3 -> 1.1" in presentation.markdown()
        assert presentation.blocks[-1].type == "approval"

    def test_valid_validation_keeps_approval(self, sample_config):
        node = PresentProposalNode(ConfigurationService(sample_config))
        proposal = ConfigurationProposal(
            summary="less conservative",
            changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1, reason="more trades")],
        )
        result = node({"proposal": proposal, "validation": ValidationResult.ok()})
        presentation = result["presentation"]
        assert any(block.type == "approval" for block in presentation.blocks)

    def test_invalid_validation_omits_approval_and_shows_errors(self, sample_config):
        node = PresentProposalNode(ConfigurationService(sample_config))
        proposal = ConfigurationProposal(
            summary="too aggressive",
            changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=15.0, reason="max aggressiveness")],
        )
        validation = ValidationResult.failed(["Field 'assets.BTC_USD.consensus.buy' value 15.0 violates constraint: too high"])
        result = node({"proposal": proposal, "validation": validation})
        presentation = result["presentation"]
        assert not any(block.type == "approval" for block in presentation.blocks)
        assert "too high" in presentation.markdown()
