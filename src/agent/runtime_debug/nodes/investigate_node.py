from __future__ import annotations

from typing import Any

from src.agent.runtime_debug.models import Evidence
from src.agent.runtime_debug.playbooks.playbook_resolver import PlaybookResolver
from src.agent.runtime_debug.state import RuntimeDebugState
from src.agent.runtime_debug.tools import RuntimeDebugToolbox


class InvestigateNode:
    def __init__(self, toolbox: RuntimeDebugToolbox, playbook_resolver: PlaybookResolver):
        self._toolbox = toolbox
        self._playbook_resolver = playbook_resolver

    def __call__(self, state: RuntimeDebugState) -> dict[str, Any]:
        error_event = state.get("error_event")
        evidence_list: list[Evidence] = list(state.get("evidence") or [])

        if not error_event:
            return {"evidence": evidence_list}

        playbook = self._playbook_resolver.resolve(error_event)
        if playbook:
            gathered = playbook.investigate(error_event, self._toolbox)
            evidence_list.extend(gathered)
        else:
            # Fallback general investigation
            evidence_list.append(
                Evidence(
                    title="Runtime Error Details",
                    description=f"{error_event.component} reported {error_event.error_type}: {error_event.message}",
                    source="runtime_exception",
                    data=error_event.to_dict(),
                )
            )

        return {"evidence": evidence_list}
