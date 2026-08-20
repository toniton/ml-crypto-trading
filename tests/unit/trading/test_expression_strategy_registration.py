from decimal import Decimal
from queue import Queue
from types import SimpleNamespace

import pytest

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.configuration.trading_config import TradingConfig
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.consensus.consensus_factor import ConsensusFactor
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.consensus.strategies.hammer_accumulation_strategy import HammerAccumulationStrategy
from src.trading.strategies.expression_strategy import ExpressionStrategy
from src.trading.strategies.strategy_registry import StrategyRegistry
from src.trading.trading_executor import TradingExecutor


def _buy_strategy(name="Test"):
    return StrategyConfig(
        name=name,
        type=StrategyType.DYNAMIC,
        action=TradeAction.BUY,
        expression="close > 100",
    )


def _sell_strategy(name):
    return StrategyConfig(
        name=name,
        type=StrategyType.DYNAMIC,
        action=TradeAction.SELL,
        expression="close < 50",
    )


def _dynamic_reference(name, enabled=True):
    return StrategyConfig(name=name, type=StrategyType.DYNAMIC, enabled=enabled)


def _static_reference(class_name, name=None, enabled=True):
    return StrategyConfig(
        name=name, type=StrategyType.STATIC, class_name=class_name, enabled=enabled
    )


def _asset(symbol, strategies=None):
    base, quote = symbol
    return Asset(
        base_ticker_symbol=base,
        quote_ticker_symbol=quote,
        quote_decimals=2,
        name=f"{base}-{quote}",
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.001,
        quantity_decimals=3,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=Timeframe.MIN1,
        strategies=strategies,
    )


def _make_executor(predefined=None, assets=None):
    consensus_manager = ConsensusManager(ConsensusFactor(buy=1.3, sell=0.5))
    container = SimpleNamespace(
        account_manager=None,
        fees_manager=None,
        order_manager=None,
        market_data_manager=None,
        consensus_manager=consensus_manager,
        session_manager=None,
        protection_manager=None,
        websocket_manager=None,
    )
    return TradingExecutor(
        assets=assets or [],
        manager_container=container,
        activity_queue=Queue(),
        strategies_registry=StrategyRegistry(predefined),
    )


def _matching_strategy(manager, action, name):
    return next(
        (
            strategy
            for strategy in manager.strategies.get(action, [])
            if strategy.name == name
        ),
        None,
    )


def _quorum_context():
    return TradingContext(
        ticker_symbol="BTC_USD",
        exchange="BACKTEST",
        starting_balance=Decimal("1000"),
    )


def _quorum_market(close="150"):
    return MarketData(
        volume=Decimal("1000"),
        high_price=Decimal("155"),
        low_price=Decimal("145"),
        close_price=Decimal(close),
        timestamp=0,
    )


def test_registers_asset_inline_strategies():
    executor = _make_executor(
        assets=[_asset(("BTC", "USD"), strategies=[_buy_strategy("Trend")])],
    )

    registered = _matching_strategy(executor.consensus_manager, TradeAction.BUY, "Trend")
    assert registered is not None
    assert isinstance(registered, ExpressionStrategy)


def test_skips_disabled_strategies():
    config = StrategyConfig(
        name="Off",
        type=StrategyType.DYNAMIC,
        action=TradeAction.SELL,
        expression="close > 100",
        enabled=False,
    )
    executor = _make_executor(
        assets=[_asset(("BTC", "USD"), strategies=[config])],
    )

    assert TradeAction.SELL not in executor.consensus_manager.strategies


def test_registers_predefined_reference():
    predefined = [_buy_strategy("Trend")]
    executor = _make_executor(
        predefined=predefined,
        assets=[_asset(("BTC", "USD"), strategies=[_dynamic_reference("Trend")])],
    )

    assert _matching_strategy(executor.consensus_manager, TradeAction.BUY, "Trend") is not None


def test_registers_builtin_static_strategy():
    executor = _make_executor(
        assets=[_asset(("BTC", "USD"), strategies=[_static_reference("HammerAccumulationStrategy")])],
    )

    registered = _matching_strategy(executor.consensus_manager, TradeAction.BUY, "HammerAccumulationStrategy")
    assert registered is not None
    assert isinstance(registered, HammerAccumulationStrategy)


def test_unknown_reference_fails_registration():
    from src.trading.strategies.strategy_resolver import StrategyResolver
    with pytest.raises(ValueError, match="NoSuchStrategy"):
        StrategyResolver.resolve_asset(
            _asset(("BTC", "USD"), strategies=[_dynamic_reference("NoSuchStrategy")]), StrategyRegistry()
        )


def test_update_config_re_registers_strategies():
    executor = _make_executor(
        assets=[_asset(("BTC", "USD"), strategies=[_buy_strategy("Old")])],
    )
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
                        {"name": "New", "type": "DYNAMIC", "action": "SELL", "expression": "close < 50"}
                    ],
                }
            ],
            "consensus": {"buy": 1.3, "sell": 0.5},
        }
    )

    executor.update_config(config)

    manager = executor.consensus_manager
    assert TradeAction.BUY not in manager.strategies
    assert _matching_strategy(manager, TradeAction.SELL, "New") is not None


def test_update_config_keeps_unrelated_consensus_and_quantity():
    executor = _make_executor(
        assets=[_asset(("BTC", "USD"), strategies=[_buy_strategy("Keep")])],
    )
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
                        {"name": "Keep", "type": "DYNAMIC", "action": "BUY", "expression": "close > 100"}
                    ],
                }
            ],
            "consensus": {"buy": 1.3, "sell": 0.5},
        }
    )

    executor.update_config(config)

    assert _matching_strategy(executor.consensus_manager, TradeAction.BUY, "Keep") is not None


def test_update_config_clears_strategies_when_removed():
    executor = _make_executor(
        assets=[_asset(("BTC", "USD"), strategies=[_buy_strategy("Old")])],
    )
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
                }
            ],
            "consensus": {"buy": 1.3, "sell": 0.5},
        }
    )

    executor.update_config(config)

    assert TradeAction.BUY not in executor.consensus_manager.strategies


def test_registered_strategy_participates_in_consensus():
    executor = _make_executor(
        assets=[_asset(("BTC", "USD"), strategies=[_buy_strategy("Trend")])],
    )
    consensus_manager = executor.consensus_manager

    assert consensus_manager.get_quorum(TradeAction.BUY, "BTC_USD", _quorum_context(), _quorum_market(), []) is True
    assert consensus_manager.get_consensus_score(TradeAction.BUY, "BTC_USD", _quorum_context(), _quorum_market(), []) == 1.0


def test_strategy_only_votes_for_assets_that_declare_it():
    executor = _make_executor(
        assets=[
            _asset(("BTC", "USD"), strategies=[_buy_strategy("Trend")]),
            _asset(("DOGE", "USD")),
        ],
    )
    consensus_manager = executor.consensus_manager

    assert consensus_manager.get_quorum(TradeAction.BUY, "BTC_USD", _quorum_context(), _quorum_market(), []) is True
    assert consensus_manager.get_quorum(TradeAction.BUY, "DOGE_USD", _quorum_context(), _quorum_market(), []) is False


def test_shared_definition_votes_for_each_declaring_asset():
    executor = _make_executor(
        assets=[
            _asset(("BTC", "USD"), strategies=[_buy_strategy("Trend")]),
            _asset(("DOGE", "USD"), strategies=[_buy_strategy("Trend")]),
        ],
    )
    trend_instances = [
        strategy
        for strategy in executor.consensus_manager.strategies[TradeAction.BUY]
        if strategy.name == "Trend"
    ]
    assert len(trend_instances) == 2
    assert all(isinstance(instance, ExpressionStrategy) for instance in trend_instances)
    assert [instance.ticker_symbols for instance in trend_instances] == [{"BTC_USD"}, {"DOGE_USD"}]


def test_disabled_asset_strategy_removed_for_asset():
    executor = _make_executor(
        assets=[
            _asset(("BTC", "USD"), strategies=[_buy_strategy("Trend")]),
            _asset(("DOGE", "USD"), strategies=[_dynamic_reference("Trend", enabled=False)]),
        ],
    )
    consensus_manager = executor.consensus_manager
    assert consensus_manager.get_quorum(TradeAction.BUY, "BTC_USD", _quorum_context(), _quorum_market(), []) is True
    assert consensus_manager.get_quorum(TradeAction.BUY, "DOGE_USD", _quorum_context(), _quorum_market(), []) is False