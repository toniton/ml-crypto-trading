from __future__ import annotations

from typing import Optional

from src.configuration.strategy_config import StrategyConfig
from src.core.registry import Registry


class StrategyRegistry(Registry[str, StrategyConfig]):
    def __init__(self, predefined: Optional[list[StrategyConfig]] = None):
        super().__init__()
        for strategy in predefined or []:
            self.register(strategy.name, strategy)
