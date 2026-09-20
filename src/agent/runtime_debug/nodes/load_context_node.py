from __future__ import annotations

from typing import Any

from src.agent.runtime_debug.state import RuntimeDebugState
from src.agent.runtime_debug.tools import RuntimeDebugToolbox


class LoadContextNode:
    def __init__(self, toolbox: RuntimeDebugToolbox):
        self._toolbox = toolbox

    def __call__(self, state: RuntimeDebugState) -> dict[str, Any]:
        incident_id = state.get("incident_id")
        error_event = state.get("error_event")
        incident = state.get("incident")

        if incident_id and not incident:
            incident = self._toolbox.get_incident(incident_id)

        if incident and not error_event:
            events = self._toolbox.get_error_events(str(incident.id), limit=1)
            if events:
                error_event = events[0]

        context: dict[str, Any] = {}
        if incident:
            context["incident_id"] = str(incident.id)
            context["asset"] = incident.asset
            context["exchange"] = incident.exchange
            context["occurrences"] = incident.occurrence_count

        if error_event and error_event.asset:
            last_commit = self._toolbox.get_last_successful_order_commit(error_event.asset)
            if last_commit:
                context["last_successful_commit"] = last_commit

        return {
            "incident": incident,
            "error_event": error_event,
            "context": context,
            "investigation_attempts": state.get("investigation_attempts", 0) + 1,
        }
