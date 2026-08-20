import pytest
from pydantic import ValidationError

from api.interfaces.trade_action import TradeAction
from src.configuration.strategy_config import StrategyType
from src.configuration.strategies_config import StrategiesConfig


def _write(tmp_path, body):
    config_file = tmp_path / "strategies.yml"
    config_file.write_text(body, encoding="utf-8")
    return str(config_file)


def test_loads_predefined_expression_strategies(tmp_path):
    path = _write(
        tmp_path,
        "strategies:\n"
        "  - name: 'RsiOversoldBuy'\n"
        "    type: 'DYNAMIC'\n"
        "    action: 'BUY'\n"
        "    expression: 'rsi(14) < 25'\n",
    )
    config = StrategiesConfig(_yaml_file=path)
    assert [strategy.name for strategy in config.strategies] == ["RsiOversoldBuy"]
    assert config.strategies[0].type is StrategyType.DYNAMIC
    assert config.strategies[0].action is TradeAction.BUY
    assert config.strategies[0].expression == "rsi(14) < 25"


def test_loads_static_strategy_references(tmp_path):
    path = _write(
        tmp_path,
        "strategies:\n"
        "  - name: 'HammerAccumulationStrategy'\n"
        "    type: 'STATIC'\n"
        "    class_name: 'HammerAccumulationStrategy'\n",
    )
    config = StrategiesConfig(_yaml_file=path)
    assert config.strategies[0].name == "HammerAccumulationStrategy"
    assert config.strategies[0].type is StrategyType.STATIC
    assert config.strategies[0].class_name == "HammerAccumulationStrategy"
    assert config.strategies[0].expression is None


def test_defaults_to_empty_registry():
    config = StrategiesConfig(strategies=[])
    assert config.strategies == []


def test_rejects_duplicate_predefined_names(tmp_path):
    path = _write(
        tmp_path,
        "strategies:\n"
        "  - name: 'rsi'\n    type: 'DYNAMIC'\n    action: 'BUY'\n    expression: 'rsi(14) < 25'\n"
        "  - name: 'rsi'\n    type: 'DYNAMIC'\n    action: 'SELL'\n    expression: 'rsi(14) > 75'\n",
    )
    with pytest.raises(ValidationError, match="Duplicate predefined strategy names"):
        StrategiesConfig(_yaml_file=path)


def test_rejects_invalid_expression(tmp_path):
    path = _write(
        tmp_path,
        "strategies:\n"
        "  - name: 'rsi'\n    type: 'DYNAMIC'\n    action: 'BUY'\n    expression: 'close >'\n",
    )
    with pytest.raises(ValidationError):
        StrategiesConfig(_yaml_file=path)