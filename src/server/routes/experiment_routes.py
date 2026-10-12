from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, status

from api.interfaces.experiment import CreateExperimentRequest, ExperimentSpec
from src.server.services.experiment_application_service import (
    ExperimentApplicationService,
)


def create_experiment_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def create_experiment_endpoint(req_body: CreateExperimentRequest, request: Request):
        srv: ExperimentApplicationService = request.app.state.experiment_service
        try:
            return await asyncio.to_thread(srv.create_experiment, req_body)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create experiment: {exc}",
            ) from exc

    @router.get("")
    async def list_experiments_endpoint(request: Request, limit: int = 50, offset: int = 0):
        srv: ExperimentApplicationService = request.app.state.experiment_service
        return await asyncio.to_thread(srv.list_experiments, limit=limit, offset=offset)

    @router.get("/{experiment_id}")
    async def get_experiment_endpoint(experiment_id: str, request: Request):
        srv: ExperimentApplicationService = request.app.state.experiment_service
        exp = await asyncio.to_thread(srv.get_experiment, experiment_id)
        if not exp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment '{experiment_id}' not found.",
            )
        return exp

    @router.put("/{experiment_id}/spec")
    async def update_experiment_spec_endpoint(experiment_id: str, spec: ExperimentSpec, request: Request):
        srv: ExperimentApplicationService = request.app.state.experiment_service
        try:
            return await asyncio.to_thread(srv.update_experiment_spec, experiment_id, spec)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update experiment spec: {exc}",
            ) from exc

    @router.delete("/{experiment_id}")
    async def delete_experiment_endpoint(experiment_id: str, request: Request):
        srv: ExperimentApplicationService = request.app.state.experiment_service
        deleted = await asyncio.to_thread(srv.delete_experiment, experiment_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment '{experiment_id}' not found.",
            )
        return {"experiment_id": experiment_id, "deleted": True}

    return router
