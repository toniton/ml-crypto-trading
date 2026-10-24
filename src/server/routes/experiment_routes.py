from __future__ import annotations

import asyncio
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request, status

from api.interfaces.evidence_proposal import GenerateExperimentProposalRequest
from api.interfaces.experiment import CreateExperimentRequest, ExperimentSpec
from src.server.services.evidence_proposal_application_service import (
    EvidenceProposalApplicationService,
)
from src.server.services.experiment_application_service import (
    ExperimentApplicationService,
)


async def _run_experiment_action(
        error_prefix: str,
        func: Callable[..., Any],
        *args: Any,
) -> Any:
    try:
        return await asyncio.to_thread(func, *args)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{error_prefix}: {exc}",
        ) from exc


def create_experiment_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def create_experiment_endpoint(req_body: CreateExperimentRequest, request: Request):
        srv: ExperimentApplicationService = request.app.state.experiment_service
        return await _run_experiment_action(
            "Failed to create experiment", srv.create_experiment, req_body
        )

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
    async def update_experiment_spec_endpoint(
            experiment_id: str,
            spec: ExperimentSpec,
            request: Request,
    ):
        srv: ExperimentApplicationService = request.app.state.experiment_service
        return await _run_experiment_action(
            "Failed to update experiment spec",
            srv.update_experiment_spec,
            experiment_id,
            spec,
        )

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

    @router.post("/{experiment_id}/start")
    async def start_experiment_endpoint(experiment_id: str, request: Request):
        srv: ExperimentApplicationService = request.app.state.experiment_service
        return await _run_experiment_action(
            "Failed to start experiment", srv.start_experiment, experiment_id
        )

    @router.post("/{experiment_id}/cancel")
    async def cancel_experiment_endpoint(experiment_id: str, request: Request):
        srv: ExperimentApplicationService = request.app.state.experiment_service
        success = await asyncio.to_thread(srv.cancel_experiment, experiment_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment '{experiment_id}' not found.",
            )
        return {"experiment_id": experiment_id, "cancelled": True}

    @router.post("/{experiment_id}/candidates/{candidate_id}/retry")
    async def retry_candidate_endpoint(
            experiment_id: str,
            candidate_id: str,
            request: Request,
    ):
        srv: ExperimentApplicationService = request.app.state.experiment_service
        return await _run_experiment_action(
            "Failed to retry candidate",
            srv.retry_candidate,
            experiment_id,
            candidate_id,
        )

    @router.post("/{experiment_id}/proposals", status_code=status.HTTP_201_CREATED)
    async def generate_experiment_proposal_endpoint(
            experiment_id: str,
            req_body: GenerateExperimentProposalRequest,
            request: Request,
    ):
        srv: EvidenceProposalApplicationService = request.app.state.evidence_proposal_service
        proposal = await _run_experiment_action(
            "Failed to generate experiment proposal",
            srv.generate_from_experiment,
            experiment_id,
            req_body,
        )
        return proposal.model_dump(mode="json")

    @router.get("/{experiment_id}/proposals")
    async def list_experiment_proposals_endpoint(
            experiment_id: str,
            request: Request,
            limit: int = 50,
            offset: int = 0,
    ):
        srv: EvidenceProposalApplicationService = request.app.state.evidence_proposal_service
        proposals = await asyncio.to_thread(
            srv.list_proposals,
            experiment_id=experiment_id,
            limit=limit,
            offset=offset,
        )
        return [p.model_dump(mode="json") for p in proposals]

    return router
