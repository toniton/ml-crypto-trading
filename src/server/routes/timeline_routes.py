from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Query

from src.server.timeline_projector import TimelineProjector


def create_timeline_router(projector: TimelineProjector) -> APIRouter:
    router = APIRouter(prefix="/api/v1/timeline", tags=["timeline"])

    @router.get("")
    async def get_timeline_endpoint(
            category: Optional[str] = Query(None, description="Filter by category"),
            severity: Optional[str] = Query(None, description="Filter by severity"),
            entity_type: Optional[str] = Query(None, description="Filter by entity type"),
            entity_id: Optional[str] = Query(None, description="Filter by entity id"),
            limit: int = Query(50, ge=1, le=500, description="Maximum items to return"),
            offset: int = Query(0, ge=0, description="Offset for pagination"),
    ):
        return projector.list_items(
            category=category,
            severity=severity,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
            offset=offset,
        )

    return router
