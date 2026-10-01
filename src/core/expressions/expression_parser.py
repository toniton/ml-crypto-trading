import ast
from typing import Any, List, Optional, Set

from src.core.expressions.schema import (
    DiagnosticSeverity,
    ExpressionDiagnostic,
    ExpressionValidationResponse,
    ExpressionValueType,
)
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
    def inspect_semantics(
            cls,
            expression: str,
            allowed_variables: Optional[Set[str]] = None,
            allowed_functions: Optional[Set[str]] = None
    ) -> ExpressionValidationResponse:
        if not expression or not expression.strip():
            return ExpressionValidationResponse(
                is_valid=True,
                inferred_type=None,
                diagnostics=[],
                referenced_variables=[],
                referenced_functions=[],
            )

        diagnostics: List[ExpressionDiagnostic] = []
        clean_expr = expression.strip()

        if len(clean_expr) > cls._MAX_FORMULA_LENGTH:
            diagnostics.append(
                ExpressionDiagnostic(
                    message=f"Formula exceeds maximum length of {cls._MAX_FORMULA_LENGTH} characters (got {len(clean_expr)}).",
                    severity=DiagnosticSeverity.ERROR,
                    start_offset=0,
                    end_offset=len(clean_expr),
                    start_line=1,
                    start_column=1,
                    end_line=1,
                    end_column=len(clean_expr) + 1,
                )
            )
            return ExpressionValidationResponse(
                is_valid=False,
                inferred_type=None,
                diagnostics=diagnostics,
                referenced_variables=[],
                referenced_functions=[],
            )

        try:
            tree = ast.parse(clean_expr, mode="eval")
        except SyntaxError as exc:
            col = exc.offset or 1
            line = exc.lineno or 1
            diagnostics.append(
                ExpressionDiagnostic(
                    message=f"Syntax Error: {exc.msg}",
                    severity=DiagnosticSeverity.ERROR,
                    start_offset=max(0, col - 1),
                    end_offset=col,
                    start_line=line,
                    start_column=col,
                    end_line=line,
                    end_column=col + 1,
                )
            )
            return ExpressionValidationResponse(
                is_valid=False,
                inferred_type=None,
                diagnostics=diagnostics,
                referenced_variables=[],
                referenced_functions=[],
            )

        referenced_variables: Set[str] = set()
        referenced_functions: Set[str] = set()

        cls._collect_and_validate_nodes(
            tree.body,
            allowed_variables=allowed_variables,
            allowed_functions=allowed_functions,
            diagnostics=diagnostics,
            referenced_variables=referenced_variables,
            referenced_functions=referenced_functions,
        )

        inferred_type = cls._infer_node_type(tree.body)
        is_valid = not any(d.severity == DiagnosticSeverity.ERROR for d in diagnostics)

        return ExpressionValidationResponse(
            is_valid=is_valid,
            inferred_type=inferred_type,
            diagnostics=diagnostics,
            referenced_variables=sorted(referenced_variables),
            referenced_functions=sorted(referenced_functions),
        )

    @classmethod
    def _collect_and_validate_nodes(  # pylint: disable=too-many-branches,too-many-statements
            cls,
            node: ast.AST,
            allowed_variables: Optional[Set[str]],
            allowed_functions: Optional[Set[str]],
            diagnostics: List[ExpressionDiagnostic],
            referenced_variables: Set[str],
            referenced_functions: Set[str],
    ) -> None:
        if isinstance(node, ast.Constant):
            return

        if isinstance(node, ast.Name):
            referenced_variables.add(node.id)
            if allowed_variables is not None and node.id not in allowed_variables:
                col_start = getattr(node, "col_offset", 0) + 1
                col_end = getattr(node, "end_col_offset", col_start + len(node.id)) + 1
                line = getattr(node, "lineno", 1)
                diagnostics.append(
                    ExpressionDiagnostic(
                        message=f"Unknown variable '{node.id}' in this context.",
                        severity=DiagnosticSeverity.ERROR,
                        start_offset=getattr(node, "col_offset", 0),
                        end_offset=getattr(node, "end_col_offset", getattr(node, "col_offset", 0) + len(node.id)),
                        start_line=line,
                        start_column=col_start,
                        end_line=getattr(node, "end_lineno", line),
                        end_column=col_end,
                    )
                )
            return

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                cls._add_node_error(node, "Only simple function calls (e.g. 'rsi(14)') are supported.", diagnostics)
                return
            if node.keywords:
                cls._add_node_error(node, "Keyword arguments are not supported in formula expressions.", diagnostics)

            func_name = node.func.id
            referenced_functions.add(func_name)

            if allowed_functions is not None and func_name not in allowed_functions:
                col_start = getattr(node.func, "col_offset", 0) + 1
                col_end = getattr(node.func, "end_col_offset", col_start + len(func_name)) + 1
                line = getattr(node.func, "lineno", 1)
                diagnostics.append(
                    ExpressionDiagnostic(
                        message=f"Unknown function '{func_name}'.",
                        severity=DiagnosticSeverity.ERROR,
                        start_offset=getattr(node.func, "col_offset", 0),
                        end_offset=getattr(node.func, "end_col_offset", getattr(node.func, "col_offset", 0) + len(func_name)),
                        start_line=line,
                        start_column=col_start,
                        end_line=getattr(node.func, "end_lineno", line),
                        end_column=col_end,
                    )
                )

            for arg in node.args:
                cls._collect_and_validate_nodes(
                    arg,
                    allowed_variables,
                    allowed_functions,
                    diagnostics,
                    referenced_variables,
                    referenced_functions,
                )
            return

        if isinstance(node, ast.BinOp):
            if not isinstance(node.op, (ast.Add, ast.Mult, ast.Sub, ast.Div)):
                cls._add_node_error(node, f"Unsupported binary operator: {type(node.op).__name__}", diagnostics)
            cls._collect_and_validate_nodes(node.left, allowed_variables, allowed_functions, diagnostics, referenced_variables, referenced_functions)
            cls._collect_and_validate_nodes(node.right, allowed_variables, allowed_functions, diagnostics, referenced_variables, referenced_functions)
            return

        if isinstance(node, ast.Compare):
            cls._collect_and_validate_nodes(node.left, allowed_variables, allowed_functions, diagnostics, referenced_variables, referenced_functions)
            for op, comparator in zip(node.ops, node.comparators):
                if not isinstance(op, (ast.Gt, ast.Lt, ast.GtE, ast.LtE, ast.Eq, ast.NotEq)):
                    cls._add_node_error(node, f"Unsupported comparison operator: {type(op).__name__}", diagnostics)
                cls._collect_and_validate_nodes(comparator, allowed_variables, allowed_functions, diagnostics, referenced_variables, referenced_functions)
            return

        if isinstance(node, ast.IfExp):
            cls._collect_and_validate_nodes(node.test, allowed_variables, allowed_functions, diagnostics, referenced_variables, referenced_functions)
            cls._collect_and_validate_nodes(node.body, allowed_variables, allowed_functions, diagnostics, referenced_variables, referenced_functions)
            cls._collect_and_validate_nodes(node.orelse, allowed_variables, allowed_functions, diagnostics, referenced_variables, referenced_functions)
            return

        if isinstance(node, ast.BoolOp):
            if not isinstance(node.op, (ast.And, ast.Or)):
                cls._add_node_error(node, f"Unsupported boolean operator: {type(node.op).__name__}", diagnostics)
            for v in node.values:
                cls._collect_and_validate_nodes(v, allowed_variables, allowed_functions, diagnostics, referenced_variables, referenced_functions)
            return

        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, (ast.USub, ast.Not)):
                cls._add_node_error(node, f"Unsupported unary operator: {type(node.op).__name__}", diagnostics)
            cls._collect_and_validate_nodes(node.operand, allowed_variables, allowed_functions, diagnostics, referenced_variables, referenced_functions)
            return

        cls._add_node_error(node, f"Unsupported expression node: {type(node).__name__}", diagnostics)

    @classmethod
    def _add_node_error(cls, node: ast.AST, message: str, diagnostics: List[ExpressionDiagnostic]) -> None:
        col_start = getattr(node, "col_offset", 0) + 1
        col_end = getattr(node, "end_col_offset", col_start + 1) + 1
        line = getattr(node, "lineno", 1)
        diagnostics.append(
            ExpressionDiagnostic(
                message=message,
                severity=DiagnosticSeverity.ERROR,
                start_offset=getattr(node, "col_offset", 0),
                end_offset=getattr(node, "end_col_offset", getattr(node, "col_offset", 0) + 1),
                start_line=line,
                start_column=col_start,
                end_line=getattr(node, "end_lineno", line),
                end_column=col_end,
            )
        )

    @classmethod
    def _infer_node_type(cls, node: ast.AST) -> ExpressionValueType:
        if isinstance(node, (ast.Compare, ast.BoolOp)):
            return ExpressionValueType.BOOLEAN
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return ExpressionValueType.BOOLEAN
        if isinstance(node, (ast.BinOp,)):
            return ExpressionValueType.NUMBER
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return ExpressionValueType.NUMBER
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return ExpressionValueType.BOOLEAN
            if isinstance(node.value, (int, float)):
                return ExpressionValueType.NUMBER
        if isinstance(node, ast.IfExp):
            return cls._infer_node_type(node.body)
        return ExpressionValueType.NUMBER

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
        comparisons = {
            ast.Gt: lambda a, b: a > b,
            ast.Lt: lambda a, b: a < b,
            ast.GtE: lambda a, b: a >= b,
            ast.LtE: lambda a, b: a <= b,
            ast.Eq: lambda a, b: a == b,
            ast.NotEq: lambda a, b: a != b,
        }
        for op_type, func in comparisons.items():
            if isinstance(op, op_type):
                return func(left, right)
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
