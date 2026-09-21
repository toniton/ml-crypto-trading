from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from src.agent.actions.models import ActionSeverity, AgentAction


class NotificationPolicy:
    """Controls frequency and deduplication of autonomous proactive messages to prevent chat spam."""

    def __init__(self, info_cooldown_seconds: float = 300.0, warning_cooldown_seconds: float = 60.0):
        self._info_cooldown_seconds = info_cooldown_seconds
        self._warning_cooldown_seconds = warning_cooldown_seconds
        self._recent_triggers: Dict[str, datetime] = {}
        self._seen_counts: Dict[str, int] = {}

    def should_deliver(self, action: AgentAction) -> bool:
        """Determines if the action should immediately be delivered as a chat message."""
        if action.severity == ActionSeverity.CRITICAL or action.reason is None:
            return True

        fingerprint = self._fingerprint(action)
        now = datetime.now(timezone.utc)
        last_delivered = self._recent_triggers.get(fingerprint)

        cooldown = (
            self._info_cooldown_seconds
            if action.severity == ActionSeverity.INFO
            else self._warning_cooldown_seconds
        )

        if last_delivered is not None:
            elapsed = (now - last_delivered).total_seconds()
            if elapsed < cooldown:
                self._seen_counts[fingerprint] = self._seen_counts.get(fingerprint, 1) + 1
                return False

        self._recent_triggers[fingerprint] = now
        self._seen_counts[fingerprint] = 1
        return True

    def get_occurrence_count(self, action: AgentAction) -> int:
        fingerprint = self._fingerprint(action)
        return self._seen_counts.get(fingerprint, 1)

    @staticmethod
    def _fingerprint(action: AgentAction) -> str:
        trigger = action.reason.trigger if action.reason else action.title
        entities = ",".join(sorted(action.reason.related_entities)) if action.reason else ""
        return f"{action.type.value}:{trigger}:{entities}"
