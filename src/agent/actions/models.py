from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ActionSafetyClass(str, Enum):
    INFORMATIONAL = "INFORMATIONAL"
    DIAGNOSTIC = "DIAGNOSTIC"
    PROPOSAL = "PROPOSAL"
    STATE_CHANGING = "STATE_CHANGING"
    TRADING_CONTROL = "TRADING_CONTROL"


class AgentActionType(str, Enum):
    SEND_MESSAGE = "SEND_MESSAGE"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    RUN_ANALYSIS = "RUN_ANALYSIS"
    RUN_BACKTEST = "RUN_BACKTEST"
    CREATE_PROPOSAL = "CREATE_PROPOSAL"
    APPLY_CONFIGURATION = "APPLY_CONFIGURATION"
    CREATE_COMMIT = "CREATE_COMMIT"


class ActionStatus(str, Enum):
    CREATED = "CREATED"
    PLANNED = "PLANNED"
    EXECUTING = "EXECUTING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ActionSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AgentPermission(str, Enum):
    READ_RUNTIME = "READ_RUNTIME"
    READ_CONFIGURATION = "READ_CONFIGURATION"
    READ_VCS = "READ_VCS"
    RUN_BACKTEST = "RUN_BACKTEST"
    SEND_CHAT_MESSAGE = "SEND_CHAT_MESSAGE"
    PROPOSE_CONFIGURATION = "PROPOSE_CONFIGURATION"
    COMMIT_CONFIGURATION = "COMMIT_CONFIGURATION"
    APPLY_CONFIGURATION = "APPLY_CONFIGURATION"
    CONTROL_TRADING = "CONTROL_TRADING"


class ActionReason(BaseModel):
    trigger: str
    evidence_ids: List[str] = Field(default_factory=list)
    related_entities: List[str] = Field(default_factory=list)


class MetricDifference(BaseModel):
    metric: str
    previous: Any
    current: Any
    difference: Optional[Any] = None
    unit: Optional[str] = None


class BacktestComparisonAction(BaseModel):
    base_commit: str
    comparison_commit: str
    asset: Optional[str] = None
    dataset_id: Optional[str] = None
    simulation_settings: dict = Field(default_factory=dict)


class BacktestComparisonResult(BaseModel):
    base_commit: str
    comparison_commit: str
    asset: Optional[str] = None
    metrics: dict = Field(default_factory=dict)
    differences: List[MetricDifference] = Field(default_factory=list)
    configuration_changes: List[dict] = Field(default_factory=list)


DEFAULT_ACTION_SAFETY_MAPPING: dict[AgentActionType, ActionSafetyClass] = {
    AgentActionType.SEND_MESSAGE: ActionSafetyClass.INFORMATIONAL,
    AgentActionType.RUN_ANALYSIS: ActionSafetyClass.DIAGNOSTIC,
    AgentActionType.RUN_BACKTEST: ActionSafetyClass.DIAGNOSTIC,
    AgentActionType.CREATE_PROPOSAL: ActionSafetyClass.PROPOSAL,
    AgentActionType.REQUEST_APPROVAL: ActionSafetyClass.PROPOSAL,
    AgentActionType.APPLY_CONFIGURATION: ActionSafetyClass.STATE_CHANGING,
    AgentActionType.CREATE_COMMIT: ActionSafetyClass.STATE_CHANGING,
}


class AgentAction(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    type: AgentActionType
    status: ActionStatus = ActionStatus.CREATED
    conversation_id: Optional[str] = None
    title: str
    description: str
    payload: dict = Field(default_factory=dict)
    reason: Optional[ActionReason] = None
    severity: ActionSeverity = ActionSeverity.INFO
    requires_approval: bool = False
    safety_class: Optional[ActionSafetyClass] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def effective_safety_class(self) -> ActionSafetyClass:
        return self.safety_class or DEFAULT_ACTION_SAFETY_MAPPING.get(
            self.type, ActionSafetyClass.INFORMATIONAL
        )


class AgentApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    conversation_id: Optional[str] = None
    agent_action_id: str
    action_type: str
    title: str
    description: str
    proposed_change: dict = Field(default_factory=dict)
    current_state: dict = Field(default_factory=dict)
    base_commit: str
    proposed_config_hash: Optional[str] = None
    asset: Optional[str] = None
    proposal_id: Optional[str] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    responded_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    decision_notes: Optional[str] = None
