from typing import Any, Callable, Dict, List, Optional

from src.core.interfaces.expression_context import ExpressionContext


class DefaultContext(ExpressionContext):
    def __init__(self, variables: Optional[Dict[str, Any]] = None, functions: Optional[Dict[str, Callable]] = None):
        self._variables = variables or {}
        self._functions = functions or {}

    def resolve_variable(self, name: str) -> Any:
        if name not in self._variables:
            raise ValueError(f"Unknown variable: {name}")
        return self._variables[name]

    def call_function(self, name: str, args: List[Any]) -> Any:
        if name not in self._functions:
            raise ValueError(f"Unknown function: {name}")
        return self._functions[name](*args)
