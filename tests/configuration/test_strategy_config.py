import pytest
from pydantic import ValidationError

from api.interfaces.trade_action import TradeAction
from src.configuration.strategy_config import StrategyConfig, StrategyType


def test_strategy_config_parses_inline_expression():
    strategy = StrategyConfig.model_validate(
        {
            "name": "HelloStrategy",
            "type": "DYNAMIC",
            "action": "BUY",
            "expression": "rsi > 0.2",
            "enabled": True,
        }
    )
    assert strategy.name == "HelloStrategy"
    assert strategy.type is StrategyType.DYNAMIC
    assert strategy.action is TradeAction.BUY
    assert strategy.expression == "rsi > 0.2"
    assert strategy.enabled is True


def test_strategy_config_enabled_defaults_to_true():
    strategy = StrategyConfig(
        name="HelloStrategy",
        type=StrategyType.DYNAMIC,
        action=TradeAction.SELL,
        expression="close > 100",
    )
    assert strategy.enabled is True


def test_strategy_config_parses_static_reference_without_expression():
    strategy = StrategyConfig(
        type=StrategyType.STATIC, class_name="HammerAccumulationStrategy"
    )
    assert strategy.name == "HammerAccumulationStrategy"
    assert strategy.type is StrategyType.STATIC
    assert strategy.action is None
    assert strategy.expression is None


def test_strategy_config_requires_class_name_for_static():
    with pytest.raises(ValidationError, match="must define a class_name"):
        StrategyConfig(name="HammerAccumulationStrategy", type=StrategyType.STATIC)


def test_strategy_config_rejects_class_name_on_dynamic():
    with pytest.raises(ValidationError, match="cannot define a class_name"):
        StrategyConfig(
            name="HelloStrategy",
            type=StrategyType.DYNAMIC,
            class_name="HammerAccumulationStrategy",
        )


def test_strategy_config_requires_action_for_expression():
    with pytest.raises(ValidationError, match="no action"):
        StrategyConfig(name="Broken", type=StrategyType.DYNAMIC, expression="close > 100")


def test_strategy_config_requires_dynamic_type_for_expression():
    with pytest.raises(ValidationError, match="type is not DYNAMIC"):
        StrategyConfig(
            name="Broken",
            type=StrategyType.STATIC,
            action=TradeAction.BUY,
            expression="close > 100",
        )


def test_strategy_config_rejects_invalid_expression():
    with pytest.raises(ValidationError):
        StrategyConfig(
            name="HelloStrategy",
            type=StrategyType.DYNAMIC,
            action=TradeAction.BUY,
            expression="close >",
        )


def test_strategy_config_rejects_unsupported_nodes():
    with pytest.raises(ValidationError):
        StrategyConfig(
            name="HelloStrategy",
            type=StrategyType.DYNAMIC,
            action=TradeAction.BUY,
            expression="__import__('os').system('ls')",
        )


def test_trading_config_rejects_duplicate_asset_strategy_names():
    from src.configuration.trading_config import TradingConfig

    with pytest.raises(ValidationError):
        TradingConfig.model_validate(
            {
                "assets": [
                    {
                        "base_ticker_symbol": "BTC",
                        "quote_ticker_symbol": "USD",
                        "quote_decimals": 2,
                        "name": "Bitcoin",
                        "exchange": "BACKTEST",
                        "min_quantity": 0.001,
                        "quantity_decimals": 3,
                        "schedule": 1,
                        "candles_timeframe": "MIN1",
                        "strategies": [
                            {
                                "name": "dup",
                                "type": "DYNAMIC",
                                "action": "BUY",
                                "expression": "close > 100",
                            },
                            {
                                "name": "dup",
                                "type": "DYNAMIC",
                                "action": "SELL",
                                "expression": "close < 50",
                            },
                        ],
                    }
                ],
                "consensus": {"buy": 1.3, "sell": 0.5},
            }
        )


def test_trading_config_parses_asset_strategies():
    from src.configuration.trading_config import TradingConfig

    config = TradingConfig.model_validate(
        {
            "assets": [
                {
                    "base_ticker_symbol": "BTC",
                    "quote_ticker_symbol": "USD",
                    "quote_decimals": 2,
                    "name": "Bitcoin",
                    "exchange": "BACKTEST",
                    "min_quantity": 0.001,
                    "quantity_decimals": 3,
                    "schedule": 1,
                    "candles_timeframe": "MIN1",
                    "strategies": [
                        {
                            "name": "momentum",
                            "type": "DYNAMIC",
                            "action": "SELL",
                            "expression": "close < ema(20)",
                        },
                        {
                            "name": "HammerAccumulationStrategy",
                            "type": "STATIC",
                            "class_name": "HammerAccumulationStrategy",
                        },
                    ],
                }
            ],
            "consensus": {"buy": 1.3, "sell": 0.5},
        }
    )

    strategies = config.assets[0].strategies
    assert strategies is not None
    assert strategies[0].name == "momentum"
    assert strategies[0].type is StrategyType.DYNAMIC
    assert strategies[0].action is TradeAction.SELL
    assert strategies[1].name == "HammerAccumulationStrategy"
    assert strategies[1].type is StrategyType.STATIC
    assert strategies[1].expression is None