import pytest

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.trading.consensus.strategies.hammer_accumulation_strategy import HammerAccumulationStrategy
from src.trading.strategies.expression_strategy import ExpressionStrategy
from src.trading.strategies.strategy_registry import StrategyRegistry
from src.trading.strategies.strategy_resolver import StrategyResolver


def _configured(name, action="BUY", expression="close > 100", enabled=True):
    return StrategyConfig(
        name=name,
        type=StrategyType.DYNAMIC,
        action=TradeAction(action),
        expression=expression,
        enabled=enabled,
    )


def _static_reference(class_name, name=None, enabled=True):
    return StrategyConfig(
        name=name, type=StrategyType.STATIC, class_name=class_name, enabled=enabled
    )


def _dynamic_reference(name, enabled=True):
    return StrategyConfig(name=name, type=StrategyType.DYNAMIC, enabled=enabled)


def _registry(*entries):
    return StrategyRegistry(list(entries))


def _asset(strategies=None, symbol=("BTC", "USD")):
    base, quote = symbol
    return Asset(
        base_ticker_symbol=base,
        quote_ticker_symbol=quote,
        quote_decimals=2,
        name=f"{base}-{quote}",
        exchange=__import__("src.exchange.interfaces.exchange_rest_manager", fromlist=["x"]).ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.001,
        quantity_decimals=3,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=Timeframe.MIN1,
        strategies=strategies,
    )


def _names(strategies):
    return [(entry.name, entry.action.value) for entry in strategies]


class TestStrategyResolver:
    def test_inline_expression_strategies_resolved_in_order(self):
        asset = _asset([
            _configured("rsi"),
            _configured("momentum", action="SELL"),
        ])

        effective = StrategyResolver.resolve_asset(asset, _registry())

        assert _names(effective) == [("rsi", "BUY"), ("momentum", "SELL")]
        assert all(isinstance(entry, ExpressionStrategy) for entry in effective)
        assert effective[0].config.expression == "close > 100"

    def test_dynamic_reference_resolves_expression_and_action_from_registry(self):
        registry = _registry(_configured("rsi", expression="rsi(14) < 25"))
        asset = _asset([_dynamic_reference("rsi")])

        effective = StrategyResolver.resolve_asset(asset, registry)

        assert _names(effective) == [("rsi", "BUY")]
        assert effective[0].config.expression == "rsi(14) < 25"

    def test_inline_definition_wins_over_registry_entry(self):
        registry = _registry(_configured("rsi", expression="rsi(14) < 25"))
        asset = _asset([_configured("rsi", expression="rsi(14) < 20")])

        effective = StrategyResolver.resolve_asset(asset, registry)

        assert effective[0].config.expression == "rsi(14) < 20"

    def test_dynamic_reference_without_registry_entry_raises(self):
        asset = _asset([_dynamic_reference("NoSuchStrategy")])

        with pytest.raises(ValueError, match="NoSuchStrategy"):
            StrategyResolver.resolve_asset(asset, _registry())

    def test_static_reference_resolves_builtin_strategy(self):
        asset = _asset([_static_reference("HammerAccumulationStrategy")])

        effective = StrategyResolver.resolve_asset(asset, _registry())

        assert len(effective) == 1
        assert isinstance(effective[0], HammerAccumulationStrategy)
        assert effective[0].action is TradeAction.BUY

    def test_static_reference_with_matching_action_is_accepted(self):
        asset = _asset([
            StrategyConfig(
                name="Hammer",
                type=StrategyType.STATIC,
                class_name="HammerAccumulationStrategy",
                action=TradeAction.BUY,
            )
        ])

        effective = StrategyResolver.resolve_asset(asset, _registry())

        assert isinstance(effective[0], HammerAccumulationStrategy)

    def test_static_reference_with_conflicting_action_raises(self):
        asset = _asset([
            StrategyConfig(
                name="Hammer",
                type=StrategyType.STATIC,
                class_name="HammerAccumulationStrategy",
                action=TradeAction.SELL,
            )
        ])

        with pytest.raises(ValueError, match="votes BUY but is configured as SELL"):
            StrategyResolver.resolve_asset(asset, _registry())

    def test_unknown_static_reference_raises(self):
        asset = _asset([_static_reference("NoSuchStrategy")])

        with pytest.raises(ValueError, match="NoSuchStrategy"):
            StrategyResolver.resolve_asset(asset, _registry())

    def test_disabled_strategies_are_skipped(self):
        asset = _asset([
            _configured("rsi"),
            _configured("off", enabled=False),
        ])

        effective = StrategyResolver.resolve_asset(asset, _registry())

        assert _names(effective) == [("rsi", "BUY")]

    def test_strategies_are_bound_to_the_declaring_asset(self):
        asset = _asset([
            _configured("rsi"),
            _static_reference("HammerAccumulationStrategy"),
        ])

        effective = StrategyResolver.resolve_asset(asset, _registry())

        assert [strategy.ticker_symbols for strategy in effective] == [{"BTC_USD"}, {"BTC_USD"}]

    def test_resolution_is_deterministic(self):
        registry = _registry(_configured("rsi", expression="rsi(14) < 25"))
        asset = _asset([_dynamic_reference("rsi"), _configured("breakout", expression="close > sma(50)")])

        first = StrategyResolver.resolve_asset(asset, registry)
        second = StrategyResolver.resolve_asset(asset, registry)

        assert _names(first) == _names(second)

    def test_asset_without_strategies_resolves_to_empty(self):
        doge = _asset([], symbol=("DOGE", "USD"))

        assert StrategyResolver.resolve_asset(doge, _registry()) == []