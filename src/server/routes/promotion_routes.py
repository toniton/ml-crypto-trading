from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException, Request, status

from api.interfaces.promotion import (
    CreateSimulatedRunRequest,
    PromoteToMainRequest,
)
from src.database.repositories.providers.postgres_promotion_repository import (
    PostgresPromotionAuditRepository,
)
from src.server.services.main_promotion_service import MainPromotionService
from src.server.services.simulation_orchestrator import SimulationOrchestrator
from src.server.services.simulation_report_service import SimulationReportService


async def _run_action(error_prefix: str, func: Callable[..., Any], *args: Any) -> Any:
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


def create_promotion_router() -> APIRouter:
    router = APIRouter(tags=["promotions"])

    @router.post("/api/v1/simulations", status_code=status.HTTP_201_CREATED)
    async def create_simulation_endpoint(req_body: CreateSimulatedRunRequest, request: Request):
        orch: SimulationOrchestrator = request.app.state.simulation_orchestrator
        return await _run_action("Failed to initiate simulated run", orch.start_simulated_run, req_body)

    @router.get("/api/v1/simulations")
    async def list_simulations_endpoint(
            request: Request,
            experiment_id: Optional[str] = None,
            candidate_id: Optional[str] = None,
            status_filter: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ):
        orch: SimulationOrchestrator = request.app.state.simulation_orchestrator
        return await asyncio.to_thread(
            orch.list_simulated_runs,
            experiment_id=experiment_id,
            candidate_id=candidate_id,
            status=status_filter,
            limit=limit,
            offset=offset,
        )

    @router.get("/api/v1/simulations/{run_id}")
    async def get_simulation_endpoint(run_id: str, request: Request):
        orch: SimulationOrchestrator = request.app.state.simulation_orchestrator
        run = await asyncio.to_thread(orch.get_simulated_run, run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Simulated run '{run_id}' not found.",
            )
        return run

    @router.post("/api/v1/simulations/{run_id}/cancel")
    async def cancel_simulation_endpoint(run_id: str, request: Request):
        orch: SimulationOrchestrator = request.app.state.simulation_orchestrator
        return await _run_action("Failed to cancel simulation", orch.cancel_simulated_run, run_id)

    @router.post("/api/v1/simulations/{run_id}/conclude")
    async def conclude_simulation_endpoint(run_id: str, request: Request):
        orch: SimulationOrchestrator = request.app.state.simulation_orchestrator
        return await _run_action("Failed to conclude simulation", orch.conclude_simulated_run, run_id)

    @router.get("/api/v1/simulations/{run_id}/report")
    async def get_simulation_report_endpoint(run_id: str, request: Request):
        rep_srv: SimulationReportService = request.app.state.simulation_report_service
        report = await asyncio.to_thread(rep_srv.get_report_by_run, run_id)
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report for simulated run '{run_id}' is not ready or not found.",
            )
        return report

    @router.post("/api/v1/promotions/preview-main")
    async def preview_promotion_endpoint(req_body: PromoteToMainRequest, request: Request):
        promo_srv: MainPromotionService = request.app.state.main_promotion_service
        return await _run_action("Failed to preview promotion", promo_srv.preview_promotion, req_body)

    @router.post("/api/v1/promotions/approve-to-main")
    async def approve_promotion_endpoint(req_body: PromoteToMainRequest, request: Request):
        promo_srv: MainPromotionService = request.app.state.main_promotion_service
        return await _run_action("Failed to promote to main", promo_srv.promote_to_main, req_body)

    @router.get("/api/v1/promotions/audit")
    async def list_promotion_audit_endpoint(
            request: Request,
            promotion_id: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ):
        with request.app.state.db_manager.get_unit_of_work() as uow:
            audit_repo = uow.get_repository(PostgresPromotionAuditRepository)
            return await asyncio.to_thread(audit_repo.list_events, promotion_id=promotion_id, limit=limit, offset=offset)

    return router
