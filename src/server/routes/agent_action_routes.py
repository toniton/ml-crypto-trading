from __future__ import annotations

import uuid
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.agent.actions.models import (
    ActionReason,
    ActionSeverity,
    AgentActionType,
    BacktestComparisonAction,
    BacktestComparisonResult,
)
from src.core.interfaces.event_bus import EventBus
from src.events.agent_event_metadata import AgentEventMetadata
from src.events.agent_events import (
    AgentActionPlanRequestedEvent,
    AgentApprovalDecisionRequestedEvent,
)
from src.server.agent_event_projector import AgentEventProjector


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
        event_bus: EventBus,
        projector: AgentEventProjector,
        compare_backtest: Optional[Callable[[BacktestComparisonAction], BacktestComparisonResult]] = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/agent", tags=["agent-actions"])

    @router.post("/actions", status_code=status.HTTP_202_ACCEPTED)
    async def create_action_endpoint(req: PlanActionRequest):
        request_id = uuid.uuid4()
        event = AgentActionPlanRequestedEvent(
            action_type=req.type.value,
            title=req.title,
            description=req.description,
            conversation_id=req.conversation_id,
            payload=req.payload,
            reason=req.reason.model_dump() if req.reason else None,
            severity=req.severity.value,
            requires_approval=req.requires_approval,
            agent_metadata=AgentEventMetadata(request_id=request_id, correlation_id=uuid.uuid4()),
        )
        event_bus.publish(event)
        return {"request_id": str(request_id), "status": "accepted"}

    @router.get("/actions")
    async def list_actions_endpoint(
            conversation_id: Optional[str] = None,
            action_status: Optional[str] = None,
            limit: int = 50,
    ):
        return projector.list_actions(
            conversation_id=conversation_id,
            status=action_status,
            limit=limit,
        )

    @router.get("/actions/{action_id}")
    async def get_action_endpoint(action_id: str):
        action = projector.get_action(action_id)
        if not action:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent action '{action_id}' not found.",
            )
        return action

    @router.get("/approvals")
    async def list_approvals_endpoint(
            approval_status: Optional[str] = None, limit: int = 50
    ):
        return projector.list_approvals(status=approval_status, limit=limit)

    @router.get("/approvals/{approval_id}")
    async def get_approval_endpoint(approval_id: str):
        approval = projector.get_approval(approval_id)
        if not approval:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Approval request '{approval_id}' not found.",
            )
        return approval

    @router.post("/approvals/{approval_id}/decision", status_code=status.HTTP_202_ACCEPTED)
    async def decide_approval_endpoint(approval_id: str, payload: ApprovalDecisionRequest):
        if payload.action.lower() not in ("approve", "reject"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Action must be 'approve' or 'reject'.",
            )
        request_id = uuid.uuid4()
        event = AgentApprovalDecisionRequestedEvent(
            approval_id=approval_id,
            decision=payload.action.lower(),
            author=payload.author or "user",
            decision_notes=payload.decision_notes,
            agent_metadata=AgentEventMetadata(request_id=request_id, correlation_id=uuid.uuid4()),
        )
        event_bus.publish(event)
        return {
            "request_id": str(request_id),
            "approval_id": approval_id,
            "status": "accepted",
        }

    @router.post("/backtest/compare")
    async def compare_backtest_endpoint(payload: BacktestComparisonAction):
        # Deprecated synchronous diagnostic RPC; retained until consumers are migrated.
        if compare_backtest is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Backtest comparison is not configured.",
            )
        try:
            result = compare_backtest(payload)
            return result.model_dump(mode="json")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to compare backtest drift: {exc}",
            ) from exc

    return router