from __future__ import annotations

from typing import List, Optional

from src.agent.runtime_debug.models import RuntimeErrorEvent
from src.agent.runtime_debug.playbooks.base_playbook import DebugPlaybook
from src.agent.runtime_debug.playbooks.order_validation_playbook import OrderValidationPlaybook
from src.agent.runtime_debug.playbooks.rate_limit_playbook import RateLimitPlaybook


class PlaybookResolver:
    def __init__(self, playbooks: Optional[List[DebugPlaybook]] = None):
        self._playbooks: List[DebugPlaybook] = playbooks or [
            OrderValidationPlaybook(),
            RateLimitPlaybook(),
        ]

    def resolve(self, event: RuntimeErrorEvent) -> Optional[DebugPlaybook]:
        for playbook in self._playbooks:
            if playbook.matches(event):
                return playbook
        return None

    def register(self, playbook: DebugPlaybook) -> None:
        self._playbooks.append(playbook)
