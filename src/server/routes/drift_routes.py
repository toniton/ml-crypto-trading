from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status

from api.interfaces.drift import DriftSnapshotResponse
from src.server.services.drift_application_service import DriftApplicationService


def create_drift_router() -> APIRouter:
    router = APIRouter(tags=["drift"])

    @router.get("/api/v1/drift/{ticker_symbol}", response_model=DriftSnapshotResponse)
    async def get_drift_snapshot_endpoint(
            ticker_symbol: str,
            request: Request,
            commit_hash: Optional[str] = None,
    ):
        service: DriftApplicationService = request.app.state.drift_service
        snapshot = await asyncio.to_thread(
            service.get_snapshot,
            ticker_symbol,
            commit_hash=commit_hash,
        )
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No drift snapshot available for '{ticker_symbol}'. Run a drift check first.",
            )
        return snapshot

    @router.post("/api/v1/drift/{ticker_symbol}/run", response_model=DriftSnapshotResponse)
    async def run_drift_check_endpoint(
            ticker_symbol: str,
            request: Request,
            commit_hash: Optional[str] = None,
    ):
        service: DriftApplicationService = request.app.state.drift_service
        try:
            snapshot = await asyncio.to_thread(
                service.run_drift_check,
                ticker_symbol,
                commit_hash=commit_hash,
            )
            scorecard_service = getattr(request.app.state, "scorecard_service", None)
            if scorecard_service is not None:
                saved = await asyncio.to_thread(
                    scorecard_service.save_snapshot,
                    symbol=ticker_symbol,
                    trigger="drift_run",
                    commit_hash=snapshot.commit_hash,
                )
                snapshot = snapshot.model_copy(update={"snapshot_id": saved.snapshot_id})
            return snapshot
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to run drift check: {exc}",
            ) from exc

    return router
