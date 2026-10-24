from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, status

from api.interfaces.walk_forward import WalkForwardRunSpec
from src.server.services.walk_forward_application_service import (
    WalkForwardApplicationService,
)


def create_walk_forward_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/walk-forward", tags=["walk-forward"])

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def start_walk_forward_run_endpoint(spec: WalkForwardRunSpec, req: Request):
        srv: WalkForwardApplicationService = req.app.state.walk_forward_service
        try:
            return await asyncio.to_thread(srv.start_run, spec)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to start walk-forward run: {exc}",
            ) from exc

    @router.get("")
    async def list_walk_forward_runs_endpoint(req: Request, limit: int = 50):
        srv: WalkForwardApplicationService = req.app.state.walk_forward_service
        return await asyncio.to_thread(srv.list_runs, limit=limit)

    @router.get("/{run_id}")
    async def get_walk_forward_run_endpoint(run_id: str, req: Request):
        srv: WalkForwardApplicationService = req.app.state.walk_forward_service
        run = await asyncio.to_thread(srv.get_run, run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Walk-forward run '{run_id}' not found.",
            )
        return run

    @router.post("/{run_id}/cancel")
    async def cancel_walk_forward_run_endpoint(run_id: str, req: Request):
        srv: WalkForwardApplicationService = req.app.state.walk_forward_service
        success = await asyncio.to_thread(srv.cancel_run, run_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Walk-forward run '{run_id}' not found or already finished.",
            )
        return {"run_id": run_id, "cancelled": True}

    return router
