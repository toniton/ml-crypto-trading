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

        if isinstance(node, ast.Compare):
            left = self._evaluate(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._evaluate(comparator)
                if isinstance(op, ast.Gt):
                    if not (left > right): return False
                elif isinstance(op, ast.Lt):
                    if not (left < right): return False
                elif isinstance(op, ast.GtE):
                    if not (left >= right): return False
                elif isinstance(op, ast.LtE):
                    if not (left <= right): return False
                elif isinstance(op, ast.Eq):
                    if not (left == right): return False
                elif isinstance(op, ast.NotEq):
                    if not (left != right): return False
                left = right
            return True

        if isinstance(node, ast.IfExp):
            test = self._evaluate(node.test)
            if test:
                return self._evaluate(node.body)
            else:
                return self._evaluate(node.orelse)

        if isinstance(node, ast.BoolOp):
            values = [self._evaluate(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)

        if isinstance(node, ast.UnaryOp):
            operand = self._evaluate(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.Not):
                return not operand

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only simple function calls are supported")
            func_name = node.func.id
            args = [self._evaluate(arg) for arg in node.args]
            return self._context.call_function(func_name, args)

        raise ValueError(f"Unsupported expression node: {type(node).__name__}")
