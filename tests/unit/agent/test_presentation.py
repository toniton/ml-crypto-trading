from src.agent.configuration.configuration_service import ConfigurationService
from src.agent import (
    ApprovalBlock,
    ConfigChange,
    ConfigurationGoal,
    ConfigurationPresentation,
    ConfigurationProposal,
    ConfigurationResult,
    GeneralResult,
    MarkdownBlock,
    ValidationResult,
)


class TestConfigurationPresentation:
    def test_blocks_render_to_markdown(self):
        presentation = ConfigurationPresentation(blocks=[
            MarkdownBlock.from_text("less conservative"),
            ApprovalBlock.build(),
        ])
        assert "less conservative" in presentation.markdown()
        assert "Approve, Reject" in presentation.markdown()

    def test_empty_presentation(self):
        assert ConfigurationPresentation.empty().markdown() == ""

    def test_presented_blocks_never_mutate_proposal(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="s",
            changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1, reason="r")],
        )
        original_changes = list(proposal.changes)
        presentation = service.build_presentation(proposal)
        assert proposal.changes == original_changes
        assert presentation.blocks[-1].type == "approval"
        diff_blocks = [b for b in presentation.blocks if b.type == "configuration_diff"]
        assert diff_blocks[0].changes[0].path == "assets.BTC_USD.consensus.buy"

    def test_build_presentation_includes_warnings(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(summary="aggro", changes=[])
        presentation = service.build_presentation(proposal, warnings=["global setting applies to all assets"])
        markdown = presentation.markdown()
        assert "Warnings:" in markdown
        assert "global setting applies to all assets" in markdown

    def test_build_presentation_with_errors_omits_approval(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="too aggressive",
            changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=15.0, reason="x")],
        )
        presentation = service.build_presentation(proposal, errors=["value must be <= 10.0"])
        assert not any(block.type == "approval" for block in presentation.blocks)
        markdown = presentation.markdown()
        assert "rejected" in markdown
        assert "value must be <= 10.0" in markdown

    def test_build_presentation_without_errors_keeps_approval(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(summary="fine", changes=[])
        presentation = service.build_presentation(proposal, errors=[])
        assert presentation.blocks[-1].type == "approval"


class TestTypedResults:
    def test_general_result_kind(self):
        assert GeneralResult().kind == "general"

    def test_configuration_result_carries_typed_fields(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="s",
            changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1, reason="r")],
        )
        presentation = service.build_presentation(proposal)
        result = ConfigurationResult(
            goal=ConfigurationGoal(objective="take more trades"),
            proposal=proposal,
            validation=ValidationResult.ok(),
            presentation=presentation,
        )
        assert result.kind == "configuration"
        assert result.presentation.markdown() != ""


class TestPresentationJsonRoundTrip:
    def test_block_json_round_trip(self):
        import json

        presentation = ConfigurationPresentation(blocks=[
            MarkdownBlock.from_text("hello"),
            ApprovalBlock.build(),
        ])
        restored = ConfigurationPresentation.model_validate_json(presentation.model_dump_json())
        assert restored.markdown() == presentation.markdown()
        assert restored.blocks[0].type == "markdown"
        assert json.loads(restored.model_dump_json())