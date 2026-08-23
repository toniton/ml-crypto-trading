from __future__ import annotations

from typing import Optional
import importlib
import pkgutil

import src.trading.consensus.strategies as strategies_package

from api.interfaces.asset import Asset
from src.core.interfaces.trading_strategy import TradingStrategy
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy
from src.trading.strategies.expression_strategy import ExpressionStrategy
from src.trading.strategies.strategy_registry import StrategyRegistry


class StrategyResolver:
    _static_classes: Optional[dict[str, type]] = None

    @classmethod
    def _builtin_strategy_classes(cls) -> dict[str, type]:
        if cls._static_classes is None:
            for (_, module_name, _) in pkgutil.iter_modules(strategies_package.__path__):
                importlib.import_module(f"{strategies_package.__name__}.{module_name}")

            cls._static_classes = {
                strategy_class.__name__: strategy_class
                for strategy_class in RuleBasedTradingStrategy.__subclasses__()
                if strategy_class is not ExpressionStrategy
            }
        return cls._static_classes

    @classmethod
    def resolve_asset(
            cls,
            asset: Asset,
            registry: Optional[StrategyRegistry] = None,
    ) -> list[TradingStrategy]:
        strategies: list[TradingStrategy] = []
        for entry in asset.strategies or []:
            if not entry.enabled:
                continue
            strategies.append(cls._resolve_entry(entry, registry, asset))
        return strategies

    @classmethod
    def _resolve_entry(
            cls, entry: StrategyConfig, registry: Optional[StrategyRegistry], asset: Asset
    ) -> TradingStrategy:
        if entry.type is StrategyType.DYNAMIC:
            return cls._resolve_dynamic(entry, registry, asset)
        return cls._resolve_static(entry, asset)

    @staticmethod
    def _bind_to_asset(strategy: TradingStrategy, asset: Asset) -> None:
        if not asset.ticker_symbol:
            raise ValueError(
                f"Cannot bind strategy '{strategy.name}': asset '{asset.name}' has no ticker symbol"
            )
        strategy.ticker_symbols = {asset.ticker_symbol}

    @classmethod
    def _resolve_dynamic(
            cls, entry: StrategyConfig, registry: Optional[StrategyRegistry], asset: Asset
    ) -> ExpressionStrategy:
        action = entry.action
        expression = entry.expression
        predefined = registry.find(entry.name) if registry else None
        if expression is None and predefined is not None:
            expression = predefined.expression
        if expression is None:
            raise ValueError(
                f"Dynamic strategy '{entry.name}' for asset {asset.ticker_symbol} has no expression: "
                f"define it inline or list it in the strategies file"
            )
        if action is None:
            if predefined is not None:
                action = predefined.action
            if action is None:
                raise ValueError(
                    f"Dynamic strategy '{entry.name}' for asset {asset.ticker_symbol} has no action"
                )
        strategy = ExpressionStrategy(
            StrategyConfig(
                name=entry.name,
                type=StrategyType.DYNAMIC,
                action=action,
                expression=expression,
            )
        )
        cls._bind_to_asset(strategy, asset)
        return strategy

    @classmethod
    def _resolve_static(cls, entry: StrategyConfig, asset: Asset) -> RuleBasedTradingStrategy:
        strategy_class = cls._builtin_strategy_classes().get(entry.class_name)
        if strategy_class is None:
            raise ValueError(
                f"Static strategy '{entry.name}' for asset {asset.ticker_symbol} references "
                f"unknown class '{entry.class_name}'"
            )
        strategy = strategy_class()
        if entry.action is not None and entry.action != strategy.action:
            raise ValueError(
                f"Static strategy '{entry.name}' for asset {asset.ticker_symbol} votes "
                f"{strategy.action.value} but is configured as {entry.action.value}"
            )
        cls._bind_to_asset(strategy, asset)
        return strategy
