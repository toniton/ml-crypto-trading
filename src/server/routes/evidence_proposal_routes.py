from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status

from api.interfaces.evidence_proposal import GenerateCommitProposalRequest
from src.server.routes.experiment_routes import _run_experiment_action
from src.server.services.evidence_proposal_application_service import (
    EvidenceProposalApplicationService,
)


def create_evidence_proposal_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/proposals/evidence", tags=["evidence-proposals"])

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def create_commit_evidence_proposal(
            req_body: GenerateCommitProposalRequest,
            request: Request,
    ):
        srv: EvidenceProposalApplicationService = request.app.state.evidence_proposal_service
        proposal = await _run_experiment_action(
            "Failed to generate evidence proposal",
            srv.generate_from_commits,
            req_body,
        )
        return proposal.model_dump(mode="json")

    @router.get("")
    async def list_evidence_proposals(
            request: Request,
            experiment_id: Optional[str] = None,
            ticker_symbol: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ):
        srv: EvidenceProposalApplicationService = request.app.state.evidence_proposal_service
        proposals = await asyncio.to_thread(
            srv.list_proposals,
            experiment_id=experiment_id,
            ticker_symbol=ticker_symbol,
            limit=limit,
            offset=offset,
        )
        return [p.model_dump(mode="json") for p in proposals]

    @router.get("/{proposal_id}")
    async def get_evidence_proposal(proposal_id: str, request: Request):
        srv: EvidenceProposalApplicationService = request.app.state.evidence_proposal_service
        proposal = await asyncio.to_thread(srv.get_proposal, proposal_id)
        if not proposal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evidence proposal '{proposal_id}' not found.",
            )
        return proposal.model_dump(mode="json")

    @router.post("/{proposal_id}/prepare-approval")
    async def prepare_evidence_proposal_approval(proposal_id: str, request: Request):
        srv: EvidenceProposalApplicationService = request.app.state.evidence_proposal_service
        return await _run_experiment_action(
            "Failed to prepare configuration approval",
            srv.prepare_configuration_approval,
            proposal_id,
        )

    return router
