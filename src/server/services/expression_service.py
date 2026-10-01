import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from api.interfaces.candle import Candle
from src.core.expressions.catalog import ExpressionCatalog
from src.core.expressions.default_context import DefaultContext
from src.core.expressions.expression_parser import ExpressionParser
from src.core.expressions.schema import (
    DiagnosticSeverity,
    ExpressionEvaluationRequest,
    ExpressionEvaluationResponse,
    ExpressionSchemaResponse,
    ExpressionValidationRequest,
    ExpressionValidationResponse,
)
from src.trading.factories.trading_expression_factory import TradingExpressionFactory


class ExpressionService:
    @staticmethod
    def get_schema() -> ExpressionSchemaResponse:
        return ExpressionCatalog.get_schema()

    @staticmethod
    def validate(request: ExpressionValidationRequest) -> ExpressionValidationResponse:
        schema = ExpressionCatalog.get_schema()
        allowed_variables: Set[str] = {
            v.name for v in schema.variables
            if request.scope in v.applicable_scopes
        }
        allowed_functions: Set[str] = {
            f.name for f in schema.functions
        }

        return ExpressionParser.inspect_semantics(
            expression=request.expression,
            allowed_variables=allowed_variables,
            allowed_functions=allowed_functions,
        )

    @classmethod
    def evaluate(cls, request: ExpressionEvaluationRequest) -> ExpressionEvaluationResponse:
        start_time = time.perf_counter()

        val_response = cls.validate(
            ExpressionValidationRequest(
                expression=request.expression,
                scope=request.scope,
            )
        )

        if not val_response.is_valid:
            error_msgs = "; ".join(
                d.message for d in val_response.diagnostics
                if d.severity == DiagnosticSeverity.ERROR
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return ExpressionEvaluationResponse(
                expression=request.expression,
                evaluated_value=None,
                is_success=False,
                error_message=error_msgs or "Validation failed",
                resolved_variables={},
                execution_time_ms=round(elapsed_ms, 3),
            )

        variables: Dict[str, Any] = ExpressionCatalog.get_sample_context_variables(request.scope)
        if request.override_variables:
            variables.update(request.override_variables)

        close_price = float(variables.get("close", 64000.0))
        high_price = float(variables.get("high", close_price * 1.01))
        low_price = float(variables.get("low", close_price * 0.99))
        sample_candles = cls._generate_sample_candles(close_price, high_price, low_price, count=50)

        functions = TradingExpressionFactory._build_functions(sample_candles)

        resolved_for_response: Dict[str, Any] = {
            k: variables[k]
            for k in val_response.referenced_variables
            if k in variables
        }

        try:
            parser = ExpressionParser(request.expression)
            context = DefaultContext(variables=variables, functions=functions)
            result = parser.parse(context)

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return ExpressionEvaluationResponse(
                expression=request.expression,
                evaluated_value=result,
                is_success=True,
                error_message=None,
                resolved_variables=resolved_for_response,
                execution_time_ms=round(elapsed_ms, 3),
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return ExpressionEvaluationResponse(
                expression=request.expression,
                evaluated_value=None,
                is_success=False,
                error_message=str(exc),
                resolved_variables=resolved_for_response,
                execution_time_ms=round(elapsed_ms, 3),
            )

    @staticmethod
    def _generate_sample_candles(close: float, high: float, low: float, count: int = 50) -> List[Candle]:
        from decimal import Decimal
        candles: List[Candle] = []
        now_ts = datetime.now(timezone.utc).timestamp()
        step = (high - low) / (count if count > 0 else 1)

        for i in range(count):
            candle_close = low + (step * i)
            candle_high = candle_close * 1.005
            candle_low = candle_close * 0.995
            candle_open = (candle_high + candle_low) / 2.0
            candles.append(
                Candle(
                    open=Decimal(str(candle_open)),
                    high=Decimal(str(candle_high)),
                    low=Decimal(str(candle_low)),
                    close=Decimal(str(candle_close)),
                    start_time=now_ts - ((count - i) * 60),
                )
            )

        if candles:
            candles[-1] = Candle(
                open=Decimal(str((high + low) / 2.0)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                start_time=now_ts,
            )

        return candles
