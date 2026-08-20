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
    name: Optional[str] = None
    type: StrategyType
    action: Optional[TradeAction] = None
    expression: Optional[str] = None
    class_name: Optional[str] = Field(default=None, min_length=1)
    enabled: bool = True

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

