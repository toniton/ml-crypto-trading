import pytest

from src.core.expressions.default_context import DefaultContext
from src.core.expressions.expression_parser import ExpressionParser


def test_basic_arithmetic():
    context = DefaultContext()
    parser = ExpressionParser(context)

    assert parser.parse("10 + 5") == 15
    assert parser.parse("10 * 5") == 50
    assert parser.parse("10 - 5") == 5
    assert parser.parse("10 / 5") == 2.0


def test_variable_resolution():
    context = DefaultContext(variables={"x": 10, "y": 5})
    parser = ExpressionParser(context)

    assert parser.parse("x + y") == 15
    assert parser.parse("x * 2") == 20


def test_function_calls():
    context = DefaultContext(
        variables={"x": 10, "y": 5},
        functions={"max": max, "min": min}
    )
    parser = ExpressionParser(context)

    assert parser.parse("max(x, y)") == 10
    assert parser.parse("min(x, y)") == 5
    assert parser.parse("max(x * 2, y + 10)") == 20


def test_nested_expressions():
    context = DefaultContext(variables={"x": 10})
    parser = ExpressionParser(context)

    assert parser.parse("(x + 2) * 3") == 36


def test_unknown_variable():
    context = DefaultContext()
    parser = ExpressionParser(context)

    with pytest.raises(ValueError, match="Unknown variable: x"):
        parser.parse("x + 1")


def test_unknown_function():
    context = DefaultContext()
    parser = ExpressionParser(context)

    with pytest.raises(ValueError, match="Unknown function: unknown_func"):
        parser.parse("unknown_func(1)")


def test_unsupported_operation():
    context = DefaultContext()
    parser = ExpressionParser(context)

    # Power operator is not supported in my implementation
    with pytest.raises(ValueError, match="Unsupported expression node: BinOp"):
        parser.parse("2 ** 3")


def test_empty_expression():
    context = DefaultContext()
    parser = ExpressionParser(context)
    assert parser.parse("") is None


def test_complex_expression():
    context = DefaultContext(
        variables={"price": 100.0, "high": 110.0, "low": 90.0},
        functions={"avg": lambda *args: sum(args) / len(args)}
    )
    parser = ExpressionParser(context)

    # Example logic: (high + low) / 2
    assert parser.parse("(high + low) / 2") == 100.0
    assert parser.parse("avg(high, low)") == 100.0
