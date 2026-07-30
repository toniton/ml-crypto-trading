import ast
from typing import Any

from src.core.interfaces.expression_context import ExpressionContext


class ExpressionParser:
    _MAX_FORMULA_LENGTH = 1000

    def __init__(self, expression: str):
        self.expression = expression
        if expression and expression.strip():
            self.validate(expression)
            self._tree = ast.parse(expression, mode="eval")
        else:
            self._tree = None

    @classmethod
    def validate(cls, expression: str) -> None:
        if not expression or not expression.strip():
            return

        if len(expression) > cls._MAX_FORMULA_LENGTH:
            raise ValueError(
                f"Formula must be at most {cls._MAX_FORMULA_LENGTH} characters. "
                f"ExpressionParser validate method got {len(expression)}."
            )

        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Invalid formula syntax: {exc}") from exc

        cls._validate_node(tree.body)

    @classmethod
    def _validate_node(cls, node: ast.AST) -> None:
        if isinstance(node, ast.Constant):
            return
        if isinstance(node, ast.Name):
            return
        if isinstance(node, ast.BinOp):
            if not isinstance(node.op, (ast.Add, ast.Mult, ast.Sub, ast.Div)):
                raise ValueError(f"Unsupported expression node: {type(node).__name__}")
            cls._validate_node(node.left)
            cls._validate_node(node.right)
            return
        if isinstance(node, ast.Compare):
            cls._validate_node(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                if not isinstance(op, (ast.Gt, ast.Lt, ast.GtE, ast.LtE, ast.Eq, ast.NotEq)):
                    raise ValueError(f"Unsupported expression node: {type(node).__name__}")
                cls._validate_node(comparator)
            return
        if isinstance(node, ast.IfExp):
            cls._validate_node(node.test)
            cls._validate_node(node.body)
            cls._validate_node(node.orelse)
            return
        if isinstance(node, ast.BoolOp):
            if not isinstance(node.op, (ast.And, ast.Or)):
                raise ValueError(f"Unsupported expression node: {type(node).__name__}")
            for v in node.values:
                cls._validate_node(v)
            return
        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, (ast.USub, ast.Not)):
                raise ValueError(f"Unsupported expression node: {type(node).__name__}")
            cls._validate_node(node.operand)
            return
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only simple function calls are supported")
            if node.keywords:
                raise ValueError("Keyword arguments are not supported")
            for arg in node.args:
                cls._validate_node(arg)
            return

        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    def parse(self, context: ExpressionContext) -> Any:
        if self._tree is None:
            return None
        return self._evaluate(self._tree.body, context)

    def _evaluate(self, node: ast.AST, context: ExpressionContext) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return context.resolve_variable(node.id)
        if isinstance(node, ast.BinOp):
            return self._evaluate_binop(node, context)
        if isinstance(node, ast.Compare):
            return self._evaluate_compare(node, context)
        if isinstance(node, ast.IfExp):
            return self._evaluate_ifexp(node, context)
        if isinstance(node, ast.BoolOp):
            return self._evaluate_boolop(node, context)
        if isinstance(node, ast.UnaryOp):
            return self._evaluate_unaryop(node, context)
        if isinstance(node, ast.Call):
            return self._evaluate_call(node, context)

        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    def _evaluate_binop(self, node: ast.BinOp, context: ExpressionContext) -> Any:
        left = self._evaluate(node.left, context)
        right = self._evaluate(node.right, context)

        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Div):
            return left / right
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    def _evaluate_compare(self, node: ast.Compare, context: ExpressionContext) -> bool:
        left = self._evaluate(node.left, context)
        for op, comparator in zip(node.ops, node.comparators):
            right = self._evaluate(comparator, context)
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

    def _evaluate_ifexp(self, node: ast.IfExp, context: ExpressionContext) -> Any:
        test = self._evaluate(node.test, context)
        if test:
            return self._evaluate(node.body, context)
        return self._evaluate(node.orelse, context)

    def _evaluate_boolop(self, node: ast.BoolOp, context: ExpressionContext) -> bool:
        values = [self._evaluate(v, context) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        return False

    def _evaluate_unaryop(self, node: ast.UnaryOp, context: ExpressionContext) -> Any:
        operand = self._evaluate(node.operand, context)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.Not):
            return not operand
        return None

    def _evaluate_call(self, node: ast.Call, context: ExpressionContext) -> Any:
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls are supported")
        if node.keywords:
            raise ValueError("Keyword arguments are not supported")
        func_name = node.func.id
        args = [self._evaluate(arg, context) for arg in node.args]
        return context.call_function(func_name, args)
