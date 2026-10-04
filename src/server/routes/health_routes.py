from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.core.interfaces.trading_engine_proxy import TradingEngineProxy


class ResolveConditionRequest(BaseModel):
    condition: str = Field(description="Condition enum string")
    scope_type: str = Field(default="global", description="Scope type: global, exchange, quote_portfolio, asset")
    scope_identifier: str = Field(default="GLOBAL", description="Scope identifier")


def create_health_router(trading_proxy: TradingEngineProxy) -> APIRouter:
    router = APIRouter(prefix="/api/v1/trading/health", tags=["trading-health"])

    @router.get("", response_model=dict[str, Any])
    async def get_health_snapshot():
        snapshot = trading_proxy.get_health_snapshot()
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trading health monitor is not active or initialized.",
            )
        return snapshot

    @router.post("/pause", response_model=dict[str, Any])
    async def pause_trading():
        snapshot = trading_proxy.pause_trading()
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to pause trading engine health state.",
            )
        return snapshot

    @router.post("/resume", response_model=dict[str, Any])
    async def resume_trading():
        snapshot = trading_proxy.resume_trading()
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to resume trading engine health state.",
            )
        return snapshot

    return router
