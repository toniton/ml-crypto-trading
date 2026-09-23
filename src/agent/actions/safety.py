from __future__ import annotations

from typing import Set

from src.agent.actions.models import (
    DEFAULT_ACTION_SAFETY_MAPPING,
    ActionSafetyClass,
    AgentActionType,
)

DEFAULT_AUTOMATION_AUTHORITY: Set[ActionSafetyClass] = {
    ActionSafetyClass.INFORMATIONAL,
    ActionSafetyClass.DIAGNOSTIC,
    ActionSafetyClass.PROPOSAL,
}


def safety_class_for_action_type(action_type: AgentActionType) -> ActionSafetyClass:
    return DEFAULT_ACTION_SAFETY_MAPPING.get(action_type, ActionSafetyClass.INFORMATIONAL)
