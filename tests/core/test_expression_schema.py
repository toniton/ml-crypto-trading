from src.core.expressions.catalog import ExpressionCatalog
from src.core.expressions.expression_parser import ExpressionParser
from src.core.expressions.schema import (
    DiagnosticSeverity,
    ExpressionEvaluationRequest,
    ExpressionScope,
    ExpressionValueType,
)
from src.server.services.expression_service import ExpressionService


def test_catalog_schema_structure():
    schema = ExpressionCatalog.get_schema()
    assert schema.language_version == "1.0.0"
    assert len(schema.operators) > 0
    assert len(schema.functions) >= 9
    assert len(schema.variables) >= 10
    assert ExpressionScope.DYNAMIC_QUANTITY in schema.scopes


def test_functions_contain_atr_rsi_sma():
    schema = ExpressionCatalog.get_schema()
    fn_names = {f.name for f in schema.functions}
    assert "atr" in fn_names
    assert "rsi" in fn_names
    assert "sma" in fn_names
    assert "ema" in fn_names
    assert "clamp" in fn_names


def test_semantic_inspection_valid_formula():
    resp = ExpressionParser.inspect_semantics(
        "equity * 0.02 / atr(14)",
        allowed_variables={"equity", "balance"},
        allowed_functions={"atr", "rsi"},
    )
    assert resp.is_valid is True
    assert resp.inferred_type == ExpressionValueType.NUMBER
    assert resp.referenced_variables == ["equity"]
    assert resp.referenced_functions == ["atr"]
    assert len(resp.diagnostics) == 0


def test_semantic_inspection_boolean_condition():
    resp = ExpressionParser.inspect_semantics(
        "close > sma(20) and rsi(14) < 30",
        allowed_variables={"close"},
        allowed_functions={"sma", "rsi"},
    )
    assert resp.is_valid is True
    assert resp.inferred_type == ExpressionValueType.BOOLEAN
    assert set(resp.referenced_variables) == {"close"}
    assert set(resp.referenced_functions) == {"rsi", "sma"}


def test_semantic_inspection_unknown_variable_diagnostic():
    resp = ExpressionParser.inspect_semantics(
        "unknown_var * 2",
        allowed_variables={"equity", "close"},
        allowed_functions={"sma"},
    )
    assert resp.is_valid is False
    assert len(resp.diagnostics) == 1
    diag = resp.diagnostics[0]
    assert diag.severity == DiagnosticSeverity.ERROR
    assert "unknown_var" in diag.message


def test_semantic_inspection_unknown_function_diagnostic():
    resp = ExpressionParser.inspect_semantics(
        "unsupported_func(14)",
        allowed_variables={"close"},
        allowed_functions={"sma", "rsi"},
    )
    assert resp.is_valid is False
    assert len(resp.diagnostics) == 1
    diag = resp.diagnostics[0]
    assert diag.severity == DiagnosticSeverity.ERROR
    assert "unsupported_func" in diag.message


def test_semantic_inspection_syntax_error():
    resp = ExpressionParser.inspect_semantics(
        "equity *",
        allowed_variables={"equity"},
        allowed_functions={},
    )
    assert resp.is_valid is False
    assert len(resp.diagnostics) > 0
    assert resp.diagnostics[0].severity == DiagnosticSeverity.ERROR


def test_expression_service_evaluate_formula():
    eval_resp = ExpressionService.evaluate(
        ExpressionEvaluationRequest(
            expression="equity * 0.02 / max(atr(14), 1.0)",
            scope=ExpressionScope.DYNAMIC_QUANTITY,
        )
    )
    assert eval_resp.is_success is True
    assert eval_resp.evaluated_value is not None
    assert "equity" in eval_resp.resolved_variables
