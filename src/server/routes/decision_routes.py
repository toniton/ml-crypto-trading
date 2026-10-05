from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_trading_decision_repository import (
    PostgresTradingDecisionRepository,
)


def create_decision_router(database_manager: DatabaseManager) -> APIRouter:
    router = APIRouter(prefix="/api/v1/decisions", tags=["trading-decisions"])

    @router.get("")
    async def list_decisions(
            ticker_symbol: Optional[str] = Query(None, description="Filter by ticker symbol"),
            exchange: Optional[str] = Query(None, description="Filter by exchange"),
            decision_status: Optional[str] = Query(None, alias="status", description="Filter by status (EXECUTED, REJECTED, SKIPPED)"),
            limit: int = Query(50, ge=1, le=500, description="Max decisions to return"),
            offset: int = Query(0, ge=0, description="Pagination offset"),
    ):
        with database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresTradingDecisionRepository)
            decisions = repo.list_decisions(
                ticker_symbol=ticker_symbol,
                exchange=exchange,
                status=decision_status,
                limit=limit,
                offset=offset,
            )
            return {
                "decisions": [d.to_dict() for d in decisions],
                "count": len(decisions),
                "limit": limit,
                "offset": offset,
            }

    @router.get("/by-order/{order_id}")
    async def get_decision_by_order(order_id: str):
        with database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresTradingDecisionRepository)
            decision = repo.get_by_order_id(order_id)
            if not decision:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No trading decision found for order '{order_id}'",
                )
            return decision.to_dict()

    @router.get("/{decision_id}")
    async def get_decision(decision_id: str):
        with database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresTradingDecisionRepository)
            decision = repo.get(decision_id)
            if not decision:
                # Also try finding by order ID as a convenient fallback
                decision = repo.get_by_order_id(decision_id)
            if not decision:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Trading decision '{decision_id}' not found",
                )
            return decision.to_dict()

    return router
