from src.agent.configuration.schema import ConfigurationSchema


class TestSchema:
    def test_get_value_root(self, sample_config):
        raw = {"dynamic_quantity": "max(min_qty, eq * 0.1)", "assets": []}
        assert ConfigurationSchema.get_value(raw, "dynamic_quantity") == "max(min_qty, eq * 0.1)"
        assert ConfigurationSchema.get_value(raw, "missing.field") is None

    def test_get_value_consensus_per_asset(self, sample_config):
        raw = {"assets": [{"base_ticker_symbol": "BTC", "quote_ticker_symbol": "USD", "consensus": {"buy": 1.3}}]}
        assert ConfigurationSchema.get_value(raw, "assets.BTC_USD.consensus.buy") == 1.3

    def test_get_value_asset_symbol(self, sample_config):
        raw = {
            "assets": [{
                "base_ticker_symbol": "BTC",
                "quote_ticker_symbol": "USD",
                "guard_config": {"max_drawdown_percentage": 0.6},
            }]
        }
        assert ConfigurationSchema.get_value(raw, "assets.BTC_USD.guard_config.max_drawdown_percentage") == 0.6
        assert ConfigurationSchema.get_value(raw, "assets.DOGE_USD.x") is None

    def test_set_value_asset_symbol(self, sample_config):
        raw = {
            "assets": [{
                "base_ticker_symbol": "BTC",
                "quote_ticker_symbol": "USD",
                "guard_config": {"max_drawdown_percentage": 0.6},
            }]
        }
        assert ConfigurationSchema.set_value(raw, "assets.BTC_USD.guard_config.max_drawdown_percentage", 0.7)
        assert raw["assets"][0]["guard_config"]["max_drawdown_percentage"] == 0.7
        assert not ConfigurationSchema.set_value(raw, "assets.NOPE_USD.x", 1)

    def test_catalog_contains_assets_and_globals(self, sample_config):
        schema = ConfigurationSchema()
        fields = schema.build_field_catalog(
            {"assets": [{"base_ticker_symbol": "BTC", "quote_ticker_symbol": "USD", "consensus": {"buy": 1.3, "sell": 0.5}}], "dynamic_quantity": "max(min_qty, eq * 0.1)"}
        )
        paths = {field.path for field in fields}
        assert "assets.BTC_USD.consensus.buy" in paths
        assert "assets.BTC_USD.guard_config.max_drawdown_percentage" in paths
        assert "dynamic_quantity" in paths

    def test_get_value_asset_strategy_name(self, sample_config):
        raw = {
            "assets": [{
                "base_ticker_symbol": "BTC",
                "quote_ticker_symbol": "USD",
                "strategies": [{
                    "name": "Trend",
                    "type": "BUY",
                    "expression": "close > 100",
                    "enabled": True,
                }],
            }]
        }
        assert ConfigurationSchema.get_value(
            raw, "assets.BTC_USD.strategies.Trend.expression"
        ) == "close > 100"
        assert ConfigurationSchema.get_value(
            raw, "assets.BTC_USD.strategies.Trend.enabled"
        ) is True
        assert ConfigurationSchema.get_value(
            raw, "assets.BTC_USD.strategies.Missing.type"
        ) is None

    def test_set_value_asset_strategy_name(self, sample_config):
        raw = {
            "assets": [{
                "base_ticker_symbol": "BTC",
                "quote_ticker_symbol": "USD",
                "strategies": [{
                    "name": "Trend",
                    "type": "BUY",
                    "expression": "close > 100",
                    "enabled": True,
                }],
            }]
        }
        assert ConfigurationSchema.set_value(
            raw, "assets.BTC_USD.strategies.Trend.enabled", False
        )
        assert raw["assets"][0]["strategies"][0]["enabled"] is False
        assert not ConfigurationSchema.set_value(
            raw, "assets.BTC_USD.strategies.Missing.enabled", True
        )

    def test_catalog_contains_strategies(self, sample_config):
        schema = ConfigurationSchema()
        fields = schema.build_field_catalog(
            {
                "assets": [{
                    "base_ticker_symbol": "BTC",
                    "quote_ticker_symbol": "USD",
                    "consensus": {"buy": 1.3, "sell": 0.5},
                    "strategies": [{
                        "name": "Trend",
                        "type": "DYNAMIC",
                        "action": "BUY",
                        "expression": "close > 100",
                        "enabled": True,
                    }],
                }],
                "dynamic_quantity": "max(min_qty, eq * 0.1)",
            }
        )
        paths = {field.path for field in fields}
        assert "assets.BTC_USD.strategies.Trend.type" in paths
        assert "assets.BTC_USD.strategies.Trend.expression" in paths
        assert "assets.BTC_USD.strategies.Trend.enabled" in paths

    def test_render_catalog_readable(self, sample_config):
        schema = ConfigurationSchema()
        rendered = schema.render_catalog(
            schema.build_field_catalog({"assets": [{"base_ticker_symbol": "BTC", "quote_ticker_symbol": "USD", "consensus": {"buy": 1.3, "sell": 0.5}}], "dynamic_quantity": "max(min_qty, eq * 0.1)"})
        )
        assert "assets.BTC_USD.consensus.buy" in rendered
        assert "editable" in rendered


class TestConstraintChecking:
    def test_range(self):
        assert ConfigurationSchema.check_constraint(0.66, "0.50 <= value <= 0.95")
        assert not ConfigurationSchema.check_constraint(0.30, "0.50 <= value <= 0.95")

    def test_comparisons(self):
        assert ConfigurationSchema.check_constraint(5, "value > 0")
        assert ConfigurationSchema.check_constraint(0.1, "value >= 0.05")
        assert not ConfigurationSchema.check_constraint(0.01, "value >= 0.05")

    def test_set(self):
        assert ConfigurationSchema.check_constraint(2, "value in {0,1,2,3,4,5}")
        assert not ConfigurationSchema.check_constraint(9, "value in {0,1,2,3,4,5}")

    def test_string(self):
        assert ConfigurationSchema.check_constraint("a=1", "value is a non-empty string")
        assert not ConfigurationSchema.check_constraint("", "value is a non-empty string")

    def test_unknown_constraint_passes(self):
        assert ConfigurationSchema.check_constraint(1, "some custom rule")
