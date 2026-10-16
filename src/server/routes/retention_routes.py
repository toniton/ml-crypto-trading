from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, status

from api.interfaces.retention import RunRequest, UpdatePolicyRequest
from src.retention.manager import (
    RetentionConfirmationRequired,
    RetentionManager,
    RetentionRunAlreadyInProgress,
)


class RetentionRouterFactory:
    """Factory creating the FastAPI router for data retention endpoints."""

    @classmethod
    def create_router(cls, retention_manager: RetentionManager) -> APIRouter:
        router = APIRouter(prefix="/api/v1/retention", tags=["Data Retention"])

        @router.get("/status")
        async def get_status():
            return await asyncio.to_thread(retention_manager.status)

        @router.get("/policies")
        async def list_policies():
            policies = await asyncio.to_thread(retention_manager.list_policies)
            return {"policies": policies}

        @router.get("/runs")
        async def list_runs(limit: int = 20):
            runs = await asyncio.to_thread(retention_manager.list_runs, limit)
            return {"runs": runs}

        @router.get("/runs/{run_id}")
        async def get_run(run_id: str):
            run = await asyncio.to_thread(retention_manager.get_run, run_id)
            if run is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Retention run '{run_id}' not found.",
                )
            return run

        @router.post("/preview")
        async def preview_run():
            try:
                return await asyncio.to_thread(retention_manager.preview)
            except RetentionRunAlreadyInProgress as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(exc),
                ) from exc

        @router.post("/run")
        async def execute_run(req_body: RunRequest):
            if not req_body.confirm:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Explicit confirmation is required to execute a retention run.",
                )
            try:
                return await asyncio.to_thread(retention_manager.execute, "api")
            except RetentionRunAlreadyInProgress as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(exc),
                ) from exc

        @router.patch("/policies/{policy_id}")
        async def update_policy(policy_id: str, req_body: UpdatePolicyRequest):
            try:
                return await asyncio.to_thread(
                    retention_manager.update_policy,
                    policy_id,
                    retention_period=req_body.retention_period,
                    retention_mode=req_body.retention_mode,
                    enabled=req_body.enabled,
                    actor=req_body.actor or "api",
                    confirm=req_body.confirm,
                )
            except KeyError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Retention policy '{policy_id}' not found.",
                ) from exc
            except RetentionConfirmationRequired as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(exc),
                ) from exc
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=str(exc),
                ) from exc

        return router


create_retention_router = RetentionRouterFactory.create_router
