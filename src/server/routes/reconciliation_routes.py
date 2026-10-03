from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter

from src.core.interfaces.trading_engine_proxy import TradingEngineProxy


def create_reconciliation_router(trading_proxy: TradingEngineProxy) -> APIRouter:
    router = APIRouter(prefix="/api/v1/reconciliation", tags=["reconciliation"])

    @router.get("/status", response_model=Dict[str, Any])
    async def get_reconciliation_status() -> Dict[str, Any]:
        return trading_proxy.get_reconciliation_status()

    @router.get("/discrepancies", response_model=List[Dict[str, Any]])
    async def get_discrepancies() -> List[Dict[str, Any]]:
        status = trading_proxy.get_reconciliation_status()
        return status.get("discrepancies", [])

    @router.post("/trigger", response_model=Dict[str, bool])
    async def trigger_reconciliation() -> Dict[str, bool]:
        triggered = trading_proxy.trigger_reconciliation()
        return {"triggered": triggered}

    @router.post("/clear", response_model=Dict[str, bool])
    async def clear_discrepancies() -> Dict[str, bool]:
        cleared = trading_proxy.clear_reconciliation_discrepancies()
        return {"cleared": cleared}

    return router
