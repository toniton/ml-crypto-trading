from pydantic.v1.dataclasses import dataclass

from src.core.interfaces.trading_strategy import TradingStrategy


@dataclass(config={"arbitrary_types_allowed": True})
class StrategySocketMessage:
    action: str
    strategy: TradingStrategy
