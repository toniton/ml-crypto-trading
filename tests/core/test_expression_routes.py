from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.routes.expression_routes import create_expression_router


def create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(create_expression_router())
    return app


def test_get_expression_schema():
    client = TestClient(create_test_app())
    response = client.get("/api/v1/expressions/schema")
    assert response.status_code == 200
    data = response.json()
    assert data["language_version"] == "1.0.0"
    assert "operators" in data
    assert "functions" in data
    assert "variables" in data
    assert "scopes" in data
    assert any(fn["name"] == "atr" for fn in data["functions"])
    assert any(var["name"] == "equity" for var in data["variables"])


def test_validate_valid_expression():
    client = TestClient(create_test_app())
    response = client.post(
        "/api/v1/expressions/validate",
        json={
            "expression": "equity * 0.02 / atr(14)",
            "scope": "dynamic_quantity"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    assert data["inferred_type"] == "number"
    assert "equity" in data["referenced_variables"]
    assert "atr" in data["referenced_functions"]
    assert len(data["diagnostics"]) == 0


def test_validate_invalid_syntax():
    client = TestClient(create_test_app())
    response = client.post(
        "/api/v1/expressions/validate",
        json={
            "expression": "equity * (",
            "scope": "dynamic_quantity"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is False
    assert len(data["diagnostics"]) > 0


def test_evaluate_dynamic_quantity():
    client = TestClient(create_test_app())
    response = client.post(
        "/api/v1/expressions/evaluate",
        json={
            "expression": "equity * 0.02 / atr(14)",
            "scope": "dynamic_quantity",
            "override_variables": {
                "equity": 20000.0,
            }
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_success"] is True
    assert data["evaluated_value"] is not None
    assert "equity" in data["resolved_variables"]
    assert data["resolved_variables"]["equity"] == 20000.0
