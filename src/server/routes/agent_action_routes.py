from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.agent.actions.executor import AgentActionExecutor
from src.agent.actions.models import (
    ActionReason,
    ActionSeverity,
    ActionStatus,
    AgentAction,
    AgentActionType,
    ApprovalStatus,
    BacktestComparisonAction,
)
from src.agent.actions.service import AgentActionService, AgentApprovalService


class PlanActionRequest(BaseModel):
    type: AgentActionType
    title: str
    description: str = ""
    conversation_id: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    reason: Optional[ActionReason] = None
    severity: ActionSeverity = ActionSeverity.INFO
    requires_approval: bool = False


class ApprovalDecisionRequest(BaseModel):
    action: str = Field(description="Decision: 'approve' or 'reject'")
    author: Optional[str] = Field(default="user", description="Author")
    decision_notes: Optional[str] = Field(default=None, description="Optional notes")


def create_agent_action_router(
        action_service: AgentActionService,
        approval_service: AgentApprovalService,
        executor: AgentActionExecutor,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/agent", tags=["agent-actions"])

    @router.post("/actions")
    async def create_action_endpoint(req: PlanActionRequest):
        action = AgentAction(
            type=req.type,
            title=req.title,
            description=req.description,
            conversation_id=req.conversation_id,
            payload=req.payload,
            reason=req.reason,
            severity=req.severity,
            requires_approval=req.requires_approval,
        )
        try:
            executed = await asyncio.to_thread(executor.plan_and_execute, action)
            return executed.model_dump(mode="json")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to execute agent action: {exc}",
            ) from exc

    @router.get("/actions")
    async def list_actions_endpoint(
            conversation_id: Optional[str] = None,
            action_status: Optional[ActionStatus] = None,
            limit: int = 50,
    ):
        actions = await asyncio.to_thread(
            action_service.list_actions,
            conversation_id=conversation_id,
            status=action_status,
            limit=limit,
        )
        return [a.model_dump(mode="json") for a in actions]

    @router.get("/actions/{action_id}")
    async def get_action_endpoint(action_id: str):
        action = await asyncio.to_thread(action_service.get_action, action_id)
        if not action:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent action '{action_id}' not found.",
            )
        return action.model_dump(mode="json")

    @router.get("/approvals")
    async def list_approvals_endpoint(
            approval_status: Optional[ApprovalStatus] = None, limit: int = 50
    ):
        approvals = await asyncio.to_thread(
            approval_service.list_approvals,
            status=approval_status,
            limit=limit,
        )
        return [a.model_dump(mode="json") for a in approvals]

    @router.get("/approvals/{approval_id}")
    async def get_approval_endpoint(approval_id: str):
        approval = await asyncio.to_thread(approval_service.get_approval, approval_id)
        if not approval:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Approval request '{approval_id}' not found.",
            )
        return approval.model_dump(mode="json")

    @router.post("/approvals/{approval_id}/decision")
    async def decide_approval_endpoint(approval_id: str, payload: ApprovalDecisionRequest):
        try:
            approval, commit_hash, warnings = await asyncio.to_thread(
                approval_service.decide_approval,
                approval_id=approval_id,
                action=payload.action.lower(),
                author=payload.author or "user",
                decision_notes=payload.decision_notes,
            )
            return {
                "approval_id": approval.id,
                "status": approval.status.value,
                "action": payload.action.lower(),
                "commit_hash": commit_hash,
                "warnings": warnings,
            }
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Approval resolution error: {exc}",
            ) from exc

    @router.post("/backtest/compare")
    async def compare_backtest_endpoint(payload: BacktestComparisonAction):
        try:
            result = await asyncio.to_thread(executor.compare_backtest_drift, payload)
            return result.model_dump(mode="json")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to compare backtest drift: {exc}",
            ) from exc

    return router
