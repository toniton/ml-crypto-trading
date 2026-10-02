from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.core.interfaces.trading_engine_proxy import (
    AssetRuntimeSnapshot,
    EngineStatus,
    TradingEngineProxy,
)


def create_engine_router(trading_proxy: TradingEngineProxy) -> APIRouter:
    router = APIRouter(prefix="/api/v1/engine", tags=["trading-engine"])

    @router.get("/status", response_model=EngineStatus)
    async def get_engine_status():
        return trading_proxy.get_status()

    @router.get("/assets", response_model=list[str])
    async def get_monitored_assets():
        return trading_proxy.list_monitored_assets()

    @router.get("/assets/{ticker_symbol}", response_model=AssetRuntimeSnapshot)
    async def get_asset_snapshot(ticker_symbol: str):
        snapshot = trading_proxy.get_asset_snapshot(ticker_symbol)
        if not snapshot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset '{ticker_symbol}' is not currently monitored or active in trading engine.",
            )
        return snapshot

    return router
