from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status

from api.interfaces.scorecard import (
    ScorecardSnapshotRecord,
    ScorecardSnapshotSummary,
    StrategyScorecardResponse,
    StrategyScorecardSummary,
)
from src.server.services.strategy_scorecard_service import StrategyScorecardService


def create_scorecard_router() -> APIRouter:
    router = APIRouter(tags=["scorecards"])

    @router.get("/api/v1/scorecards", response_model=list[StrategyScorecardSummary])
    async def list_scorecards_endpoint(
            request: Request,
            branch: str = "main",
    ):
        service: StrategyScorecardService = request.app.state.scorecard_service
        return await asyncio.to_thread(service.list_scorecards, branch=branch)

    @router.get("/api/v1/scorecards/snapshots", response_model=list[ScorecardSnapshotSummary])
    async def list_scorecard_snapshots_endpoint(
            request: Request,
            symbol: Optional[str] = None,
            limit: int = 50,
    ):
        service: StrategyScorecardService = request.app.state.scorecard_service
        return await asyncio.to_thread(service.list_snapshots, symbol=symbol, limit=limit)

    @router.get(
        "/api/v1/scorecards/snapshots/{snapshot_id}",
        response_model=ScorecardSnapshotRecord,
    )
    async def get_scorecard_snapshot_endpoint(
            snapshot_id: str,
            request: Request,
    ):
        service: StrategyScorecardService = request.app.state.scorecard_service
        record = await asyncio.to_thread(service.get_snapshot, snapshot_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scorecard snapshot '{snapshot_id}' not found.",
            )
        return record

    @router.post(
        "/api/v1/scorecards/{ticker_symbol}/snapshots",
        response_model=ScorecardSnapshotRecord,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_scorecard_snapshot_endpoint(
            ticker_symbol: str,
            request: Request,
            commit_hash: Optional[str] = None,
            branch: str = "main",
    ):
        service: StrategyScorecardService = request.app.state.scorecard_service
        return await asyncio.to_thread(
            service.save_snapshot,
            symbol=ticker_symbol,
            trigger="manual",
            commit_hash=commit_hash,
            branch=branch,
        )

    @router.get("/api/v1/scorecards/{ticker_symbol}", response_model=StrategyScorecardResponse)
    async def get_scorecard_endpoint(
            ticker_symbol: str,
            request: Request,
            commit_hash: Optional[str] = None,
            branch: str = "main",
    ):
        service: StrategyScorecardService = request.app.state.scorecard_service
        try:
            return await asyncio.to_thread(
                service.get_scorecard,
                symbol=ticker_symbol,
                commit_hash=commit_hash,
                branch=branch,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    return router
