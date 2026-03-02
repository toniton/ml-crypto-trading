import ast
from typing import Any

from src.core.interfaces.expression_context import ExpressionContext


class ExpressionParser:
    def __init__(self, context: ExpressionContext):
        self._context = context

    def parse(self, expression: str) -> Any:
        if not expression:
            return None
        tree = ast.parse(expression, mode="eval")
        return self._evaluate(tree.body)

    def _evaluate(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return self._context.resolve_variable(node.id)
        if isinstance(node, ast.BinOp):
            return self._evaluate_binop(node)
        if isinstance(node, ast.Compare):
            return self._evaluate_compare(node)
        if isinstance(node, ast.IfExp):
            return self._evaluate_ifexp(node)
        if isinstance(node, ast.BoolOp):
            return self._evaluate_boolop(node)
        if isinstance(node, ast.UnaryOp):
            return self._evaluate_unaryop(node)
        if isinstance(node, ast.Call):
            return self._evaluate_call(node)

        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    def _evaluate_binop(self, node: ast.BinOp) -> Any:
        left = self._evaluate(node.left)
        right = self._evaluate(node.right)

        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Div):
            return left / right
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    def _evaluate_compare(self, node: ast.Compare) -> bool:
        left = self._evaluate(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self._evaluate(comparator)
            if not self._apply_comparison(left, op, right):
                return False
            left = right
        return True

    def _apply_comparison(self, left: Any, op: ast.cmpop, right: Any) -> bool:
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.GtE):
            return left >= right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        return False

    def _evaluate_ifexp(self, node: ast.IfExp) -> Any:
        test = self._evaluate(node.test)
        if test:
            return self._evaluate(node.body)
        return self._evaluate(node.orelse)

    def _evaluate_boolop(self, node: ast.BoolOp) -> bool:
        values = [self._evaluate(v) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        return False

    def _evaluate_unaryop(self, node: ast.UnaryOp) -> Any:
        operand = self._evaluate(node.operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.Not):
            return not operand
        return None

    def _evaluate_call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls are supported")
        func_name = node.func.id
        args = [self._evaluate(arg) for arg in node.args]
        return self._context.call_function(func_name, args)
