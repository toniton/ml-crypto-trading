from fastapi import APIRouter

from src.core.expressions.schema import (
    ExpressionEvaluationRequest,
    ExpressionEvaluationResponse,
    ExpressionSchemaResponse,
    ExpressionValidationRequest,
    ExpressionValidationResponse,
)
from src.server.services.expression_service import ExpressionService


def create_expression_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/expressions", tags=["expressions"])

    @router.get("/schema", response_model=ExpressionSchemaResponse)
    async def get_schema():
        return ExpressionService.get_schema()

    @router.post("/validate", response_model=ExpressionValidationResponse)
    async def validate_expression(request: ExpressionValidationRequest):
        return ExpressionService.validate(request)

    @router.post("/evaluate", response_model=ExpressionEvaluationResponse)
    async def evaluate_expression(request: ExpressionEvaluationRequest):
        return ExpressionService.evaluate(request)

    return router
