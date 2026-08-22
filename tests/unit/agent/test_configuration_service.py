from src.agent.configuration.configuration_service import ConfigurationService
from src.agent import ConfigChange, ConfigurationProposal


class TestConfigurationService:
    def test_loads_yaml(self, sample_config):
        service = ConfigurationService(sample_config)
        raw = service.load_raw_config()
        assert raw["assets"][0]["consensus"]["buy"] == 1.3
        assert raw["assets"][0]["base_ticker_symbol"] == "BTC"

    def test_valid_proposal(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="Take more trades.",
            changes=[
                ConfigChange(
                    path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1,
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
                ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=15.0, reason="max aggressiveness"),
            ],
        )
        validation = service.validate_proposal(proposal)
        assert validation.valid is False
        assert any("violates constraint" in error for error in validation.errors)

    def test_rejects_type_mismatch(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="wrong type",
            changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value="high", reason="x")],
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
                ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=0.9, new_value=1.5, reason="x"),
            ],
        )
        _, warnings = service.apply_proposal(proposal)
        assert len(warnings) == 1
        assert "rebased" in warnings[0]

    def test_render_diff(self, sample_config):
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="less conservative",
            changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.05, reason="more trades")],
            risks=["Noise"],
            expected_effect="more signals",
        )
        rendered = service.render_proposed_diff(proposal)
        assert "assets.BTC_USD.consensus.buy: 1.3 -> 1.05" in rendered
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


class TestValueNormalization:
    def test_string_number_is_coerced_before_being_written(self, sample_config):
        # The LLM may propose "1.1" for a float field. Validation accepts it, and
        # without normalization the *string* lands in the YAML.
        service = ConfigurationService(sample_config)
        proposal = ConfigurationProposal(
            summary="less conservative",
            changes=[
                ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value="1.1", reason="r"),
            ],
        )

        validation = service.validate_proposal(proposal)
        assert validation.valid is True
        assert proposal.changes[0].new_value == 1.1
        assert isinstance(proposal.changes[0].new_value, float)

        patched, _ = service.apply_proposal(proposal)
        assert patched["assets"][0]["consensus"]["buy"] == 1.1
        assert isinstance(patched["assets"][0]["consensus"]["buy"], float)


class TestPreExistingConfigErrors:
    @staticmethod
    def _config_with_stale_value(tmp_path, sample_config):
        import yaml

        raw = yaml.safe_load(open(sample_config, encoding="utf-8"))
        raw["assets"][0]["guard_config"]["max_drawdown_percentage"] = 5.0
        broken = tmp_path / "broken.yaml"
        broken.write_text(yaml.safe_dump(raw), encoding="utf-8")
        return str(broken)

    def test_unrelated_stale_value_does_not_reject_the_proposal(self, tmp_path, sample_config):
        # Validation is wholesale, so an already-invalid value elsewhere in the file
        # must not make every proposal unfixable.
        service = ConfigurationService(self._config_with_stale_value(tmp_path, sample_config))
        proposal = ConfigurationProposal(
            summary="less conservative",
            changes=[
                ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1, reason="r"),
            ],
        )

        validation = service.validate_proposal(proposal)
        assert validation.valid is True
        assert any("already invalid" in warning for warning in validation.warnings)

    def test_stale_value_is_still_enforced_when_the_proposal_touches_it(self, tmp_path, sample_config):
        service = ConfigurationService(self._config_with_stale_value(tmp_path, sample_config))
        proposal = ConfigurationProposal(
            summary="worse",
            changes=[
                ConfigChange(
                    path="assets.BTC_USD.guard_config.max_drawdown_percentage",
                    old_value=5.0, new_value=9.0, reason="r",
                ),
            ],
        )

        validation = service.validate_proposal(proposal)
        assert validation.valid is False
        assert any("violates constraint" in error for error in validation.errors)


class TestErrorMessages:
    CONFIG_WITH_STRATEGY = """
assets:
  - name: "Bitcoin (Crypto.com)"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 0.00005
    quote_decimals: 2
    quantity_decimals: 5
    candles_timeframe: "MIN1"
    schedule: 1
    consensus:
      buy: 1.3
      sell: 0.5
    strategies:
      - name: "Trend"
        type: "DYNAMIC"
        action: "BUY"
        expression: "close > 100"
        enabled: true
dynamic_quantity: "max(min_qty, eq * 0.1)"
"""

    def test_model_level_error_reports_the_changed_leaf(self, tmp_path):
        # Model validators report the whole model as their input; the message
        # should still point at the value the agent actually proposed.
        config_file = tmp_path / "with-strategy.yaml"
        config_file.write_text(self.CONFIG_WITH_STRATEGY, encoding="utf-8")
        service = ConfigurationService(str(config_file))
        proposal = ConfigurationProposal(
            summary="switch strategy type",
            changes=[
                ConfigChange(
                    path="assets.BTC_USD.strategies.Trend.type",
                    old_value="DYNAMIC", new_value="STATIC", reason="r",
                ),
            ],
        )

        validation = service.validate_proposal(proposal)
        assert validation.valid is False
        assert any("value 'STATIC'" in error for error in validation.errors)
        assert not any("{" in error for error in validation.errors)

    def test_empty_expression_is_rejected(self, tmp_path):
        config_file = tmp_path / "with-strategy.yaml"
        config_file.write_text(self.CONFIG_WITH_STRATEGY, encoding="utf-8")
        service = ConfigurationService(str(config_file))
        proposal = ConfigurationProposal(
            summary="blank the expression",
            changes=[
                ConfigChange(
                    path="assets.BTC_USD.strategies.Trend.expression",
                    old_value="close > 100", new_value="", reason="r",
                ),
            ],
        )

        assert service.validate_proposal(proposal).valid is False
