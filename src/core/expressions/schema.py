from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExpressionScope(str, Enum):
    DYNAMIC_QUANTITY = "dynamic_quantity"
    ENTRY_CONDITION = "entry_condition"
    EXIT_CONDITION = "exit_condition"
    GUARD_CONDITION = "guard_condition"
    GENERAL_CALCULATION = "general_calculation"


class ExpressionValueType(str, Enum):
    NUMBER = "number"
    BOOLEAN = "boolean"
    SERIES = "series"
    ANY = "any"


class OperatorSpec(BaseModel):
    symbol: str = Field(description="Operator token, e.g. '+', '==', 'and'")
    name: str = Field(description="Display name of operator")
    category: str = Field(description="Category: 'Arithmetic', 'Comparison', 'Logical', 'Unary'")
    precedence: int = Field(description="Operator precedence order")
    description: str = Field(description="Explanation of behavior")
    example: str = Field(description="Usage example")


class SyntaxConstructSpec(BaseModel):
    name: str = Field(description="Name of construct, e.g. 'Ternary Conditional'")
    syntax_pattern: str = Field(description="Pattern, e.g. '<expr1> if <condition> else <expr2>'")
    description: str = Field(description="Explanation of the construct")
    example: str = Field(description="Working formula example")


class ParameterSpec(BaseModel):
    name: str = Field(description="Parameter name")
    type: ExpressionValueType = Field(description="Expected data type")
    description: str = Field(description="Description of what this parameter represents")
    required: bool = Field(default=True, description="Whether parameter is required")
    default: Optional[Any] = Field(default=None, description="Default value if optional")
    min_value: Optional[float] = Field(default=None, description="Minimum allowable value")


class FunctionSpec(BaseModel):
    name: str = Field(description="Function identifier, e.g. 'rsi', 'sma', 'atr'")
    display_name: str = Field(description="Human readable name, e.g. 'Relative Strength Index (RSI)'")
    category: str = Field(description="Category: 'Technical Indicators', 'Math & Statistics', 'Utility'")
    description: str = Field(description="Detailed documentation with formula intuition")
    parameters: List[ParameterSpec] = Field(default_factory=list, description="Positional arguments")
    return_type: ExpressionValueType = Field(description="Return type of the function")
    signature: str = Field(description="Human readable signature, e.g. 'rsi(period: int = 14) -> number'")
    example: str = Field(description="Working example expression")
    autocomplete_snippet: str = Field(description="Monaco/LSP snippet with tabstops, e.g. 'rsi(${1:14})'")


class VariableSpec(BaseModel):
    name: str = Field(description="Variable identifier, e.g. 'equity', 'close', 'pnl'")
    display_name: str = Field(description="Human-readable label, e.g. 'Total Equity'")
    category: str = Field(description="Category: 'Market Data', 'Account & Portfolio', 'Position State', 'Consensus & Signals', 'Asset Rules'")
    type: ExpressionValueType = Field(description="Variable data type")
    unit: Optional[str] = Field(default=None, description="Unit symbol or code, e.g. '$', 'USDC', '%', 'qty'")
    description: str = Field(description="Description and calculation method")
    example_value: Any = Field(description="Realistic sample value for UI display and live testing")
    applicable_scopes: List[ExpressionScope] = Field(
        default_factory=lambda: list(ExpressionScope),
        description="Scopes where this variable is available"
    )


class ExpressionSchemaResponse(BaseModel):
    language_version: str = Field(default="1.0.0")
    max_expression_length: int = Field(default=1000)
    operators: List[OperatorSpec]
    syntax_constructs: List[SyntaxConstructSpec]
    functions: List[FunctionSpec]
    variables: List[VariableSpec]
    scopes: Dict[ExpressionScope, List[str]] = Field(
        description="Map of scope to allowed variable and function names"
    )


class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ExpressionDiagnostic(BaseModel):
    message: str
    severity: DiagnosticSeverity
    start_offset: int
    end_offset: int
    start_line: int = 1
    start_column: int
    end_line: int = 1
    end_column: int


class ExpressionValidationRequest(BaseModel):
    expression: str
    scope: ExpressionScope = ExpressionScope.GENERAL_CALCULATION


class ExpressionValidationResponse(BaseModel):
    is_valid: bool
    inferred_type: Optional[ExpressionValueType] = None
    diagnostics: List[ExpressionDiagnostic] = Field(default_factory=list)
    referenced_variables: List[str] = Field(default_factory=list)
    referenced_functions: List[str] = Field(default_factory=list)


class ExpressionEvaluationRequest(BaseModel):
    expression: str
    scope: ExpressionScope = ExpressionScope.DYNAMIC_QUANTITY
    symbol: Optional[str] = Field(default=None, description="Asset symbol to pull live context for")
    override_variables: Optional[Dict[str, Any]] = Field(default=None, description="Custom variable overrides for dry-run")


class ExpressionEvaluationResponse(BaseModel):
    expression: str
    evaluated_value: Optional[Any] = None
    is_success: bool
    error_message: Optional[str] = None
    resolved_variables: Dict[str, Any] = Field(default_factory=dict, description="Resolved values of referenced variables")
    execution_time_ms: float = 0.0
