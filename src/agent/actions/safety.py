from __future__ import annotations

from enum import Enum
from typing import Set

from src.agent.actions.models import AgentActionType


class ActionSafetyClass(str, Enum):
    INFORMATIONAL = "INFORMATIONAL"
    DIAGNOSTIC = "DIAGNOSTIC"
    PROPOSAL = "PROPOSAL"
    STATE_CHANGING = "STATE_CHANGING"
    TRADING_CONTROL = "TRADING_CONTROL"


DEFAULT_AUTOMATION_AUTHORITY: Set[ActionSafetyClass] = {
    ActionSafetyClass.INFORMATIONAL,
    ActionSafetyClass.DIAGNOSTIC,
    ActionSafetyClass.PROPOSAL,
}


def safety_class_for_action_type(action_type: "AgentActionType") -> ActionSafetyClass:
    # Imported lazily to avoid a circular import with src.agent.actions.models.
    from src.agent.actions.models import AgentActionType

    mapping = {
        AgentActionType.SEND_MESSAGE: ActionSafetyClass.INFORMATIONAL,
        AgentActionType.RUN_ANALYSIS: ActionSafetyClass.DIAGNOSTIC,
        AgentActionType.RUN_BACKTEST: ActionSafetyClass.DIAGNOSTIC,
        AgentActionType.CREATE_PROPOSAL: ActionSafetyClass.PROPOSAL,
        AgentActionType.REQUEST_APPROVAL: ActionSafetyClass.PROPOSAL,
        AgentActionType.APPLY_CONFIGURATION: ActionSafetyClass.STATE_CHANGING,
        AgentActionType.CREATE_COMMIT: ActionSafetyClass.STATE_CHANGING,
    }
    return mapping.get(action_type, ActionSafetyClass.INFORMATIONAL)
