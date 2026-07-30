import pytest

from src.core.expressions.default_context import DefaultContext
from src.core.expressions.expression_parser import ExpressionParser


def test_basic_arithmetic():
    context = DefaultContext()

    assert ExpressionParser("10 + 5").parse(context) == 15
    assert ExpressionParser("10 * 5").parse(context) == 50
    assert ExpressionParser("10 - 5").parse(context) == 5
    assert ExpressionParser("10 / 5").parse(context) == 2.0


def test_variable_resolution():
    context = DefaultContext(variables={"x": 10, "y": 5})

    assert ExpressionParser("x + y").parse(context) == 15
    assert ExpressionParser("x * 2").parse(context) == 20


def test_function_calls():
    context = DefaultContext(
        variables={"x": 10, "y": 5},
        functions={"max": max, "min": min}
    )

    assert ExpressionParser("max(x, y)").parse(context) == 10
    assert ExpressionParser("min(x, y)").parse(context) == 5
    assert ExpressionParser("max(x * 2, y + 10)").parse(context) == 20


def test_nested_expressions():
    context = DefaultContext(variables={"x": 10})

    assert ExpressionParser("(x + 2) * 3").parse(context) == 36


def test_unknown_variable():
    context = DefaultContext()
    parser = ExpressionParser("x + 1")

    with pytest.raises(ValueError, match="Unknown variable: x"):
        parser.parse(context)


def test_unknown_function():
    context = DefaultContext()
    parser = ExpressionParser("unknown_func(1)")

    with pytest.raises(ValueError, match="Unknown function: unknown_func"):
        parser.parse(context)


def test_unsupported_operation():
    # Power operator is not supported in my implementation
    with pytest.raises(ValueError, match="Unsupported expression node: BinOp"):
        ExpressionParser("2 ** 3")


def test_empty_expression():
    context = DefaultContext()
    parser = ExpressionParser("")
    assert parser.parse(context) is None


def test_complex_expression():
    context = DefaultContext(
        variables={"price": 100.0, "high": 110.0, "low": 90.0},
        functions={"avg": lambda *args: sum(args) / len(args)}
    )

    # Example logic: (high + low) / 2
    assert ExpressionParser("(high + low) / 2").parse(context) == 100.0
    assert ExpressionParser("avg(high, low)").parse(context) == 100.0


class TestValidate:
    def test_validates_simple_expression(self):
        ExpressionParser.validate("min_qty * 2")

    def test_validates_empty_string(self):
        ExpressionParser.validate("")

    def test_validates_complex_formula(self):
        ExpressionParser.validate(
            "max(min_qty, min((equity * risk_pct / close) * signal * "
            "(1.5 if rsi(14) > 60 else 1) * (1.5 if pnl > 0 else 0.5), "
            "equity * 0.1 / close))"
        )

    def test_rejects_invalid_syntax(self):
        with pytest.raises(ValueError, match="Invalid formula syntax"):
            ExpressionParser.validate("min_qty ++")

    def test_rejects_unsupported_node_type(self):
        with pytest.raises(ValueError, match="Unsupported expression node"):
            ExpressionParser.validate("[x for x in range(10)]")

    def test_rejects_keyword_arguments(self):
        with pytest.raises(ValueError, match="Keyword arguments"):
            ExpressionParser.validate("max(1, 2, key=3)")

    def test_rejects_attribute_call(self):
        with pytest.raises(ValueError, match="Only simple function calls"):
            ExpressionParser.validate("obj.method()")
