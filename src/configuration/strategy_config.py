from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from api.interfaces.trade_action import TradeAction
from src.core.expressions.expression_parser import ExpressionParser


class StrategyType(str, Enum):
    STATIC = "STATIC"
    DYNAMIC = "DYNAMIC"


class StrategyConfig(BaseModel):
    name: Optional[str] = Field(
        default=None,
        description="Unique identifier of the strategy within the asset.",
        json_schema_extra={"mutable": False},
    )
    type: StrategyType = Field(
        description="How the strategy is implemented: STATIC (built-in Python strategy) or DYNAMIC (expression).",
        json_schema_extra={"mutable": True},
    )
    action: Optional[TradeAction] = Field(
        default=None,
        description="Direction the strategy votes for: BUY or SELL.",
        json_schema_extra={"mutable": True},
    )
    expression: Optional[str] = Field(
        default=None,
        description="Expression evaluated by a DYNAMIC strategy. True means it votes in its direction. May reference market, position and indicator variables.",
        json_schema_extra={"mutable": True},
    )
    class_name: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Fully-qualified class name for STATIC strategies.",
        json_schema_extra={"mutable": True},
    )
    enabled: bool = Field(
        default=True,
        description="Whether the strategy is active in the consensus calculation.",
        json_schema_extra={"mutable": True},
    )

    @model_validator(mode="after")
    def _validate_strategy(self) -> StrategyConfig:
        if self.type is StrategyType.DYNAMIC:
            if self.name is None:
                raise ValueError("Dynamic strategy must define a name")
            if self.class_name is not None:
                raise ValueError(
                    f"Dynamic strategy '{self.name}' cannot define a class_name"
                )
            if self.expression is not None:
                if self.action is None:
                    raise ValueError(f"Strategy '{self.name}' defines an expression but no action")
                ExpressionParser.validate(self.expression)
        else:
            if self.expression is not None:
                raise ValueError(
                    f"Strategy '{self.name}' defines an expression but type is not {StrategyType.DYNAMIC.value}"
                )
            if self.class_name is None:
                raise ValueError(
                    f"Strategy '{self.name or ''}' of type {StrategyType.STATIC.value} must define a class_name"
                )
            if self.name is None:
                self.name = self.class_name
        return self

