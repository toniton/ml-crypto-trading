from src.agent.configuration.configuration_service import ConfigurationService
from src.agent import ConfigChange, ConfigurationProposal


class TestConfigurationService:
    def test_loads_yaml(self, sample_config):
        service = ConfigurationService(sample_config)
        raw = service.load_raw_config()
        assert raw["consensus"]["buy"] == 1.3
        assert raw["assets"][0]["base_ticker_symbol"] == "BTC"

    def test_valid_proposal(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="Take more trades.",
            changes=[
                ConfigChange(
                    path="consensus.buy", old_value=1.3, new_value=1.1,
                    reason="Lower buy threshold allows more signals.",
                )
            ],
            risks=["Lower-quality signals."],
            expected_effect="More buy signals.",
        )
        validation = service.validate_proposal(proposal)
        assert validation.valid is True
        assert validation.errors == []

    def test_rejects_unknown_path(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="bad",
            changes=[ConfigChange(path="does.not.exist", old_value=None, new_value=1, reason="nope")],
        )
        validation = service.validate_proposal(proposal)
        assert validation.valid is False
        assert any("Unknown configuration path" in error for error in validation.errors)

    def test_rejects_llm_path_as_unknown(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="leak",
            changes=[ConfigChange(path="llm.api_key", old_value="super-secret", new_value="hacked", reason="x")],
        )
        validation = service.validate_proposal(proposal)
        assert validation.valid is False
        assert any("Unknown configuration path" in error for error in validation.errors)

    def test_rejects_constraint_violation(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="too aggressive",
            changes=[
                ConfigChange(path="consensus.buy", old_value=1.3, new_value=15.0, reason="max aggressiveness"),
            ],
        )
        validation = service.validate_proposal(proposal)
        assert validation.valid is False
        assert any("violates constraint" in error for error in validation.errors)

    def test_rejects_type_mismatch(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="wrong type",
            changes=[ConfigChange(path="consensus.buy", old_value=1.3, new_value="high", reason="x")],
        )
        validation = service.validate_proposal(proposal)
        assert validation.valid is False

    def test_apply_proposal_returns_patched_copy(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="update schedule",
            changes=[
                ConfigChange(path="assets.BTC_USD.schedule", old_value=1, new_value=2, reason="hourly cadence"),
            ],
        )
        updated, warnings = service.apply_proposal(proposal)
        assert updated["assets"][0]["schedule"] == 2
        assert warnings == []

    def test_apply_proposal_warns_on_stale_old_value(self, sample_config, tmp_path):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="stale",
            changes=[
                ConfigChange(path="consensus.buy", old_value=0.9, new_value=1.5, reason="x"),
            ],
        )
        _, warnings = service.apply_proposal(proposal)
        assert len(warnings) == 1
        assert "rebased" in warnings[0]

    def test_render_diff(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="less conservative",
            changes=[ConfigChange(path="consensus.buy", old_value=1.3, new_value=1.05, reason="more trades")],
            risks=["Noise"],
            expected_effect="more signals",
        )
        rendered = service.render_proposed_diff(proposal)
        assert "consensus.buy: 1.3 -> 1.05" in rendered
        assert "Noise" in rendered

    def test_render_diff_with_warnings(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(summary="aggro", changes=[ConfigChange(path="dynamic_quantity", old_value="a", new_value="b", reason="r")])
        rendered = service.render_proposed_diff(proposal, warnings=["global setting applies to all assets"])
        assert "Warnings:" in rendered
        assert "global setting applies to all assets" in rendered

    def test_render_catalog(self, sample_config):
        service = ConfigurationService(sample_config)
        rendered = service.render_catalog()
        assert "assets.BTC_USD.guard_config.max_drawdown_percentage" in rendered

    def test_proposal_without_changes_invalid(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(summary="nothing", changes=[])
        assert service.validate_proposal(proposal).valid is False
