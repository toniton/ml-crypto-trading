from __future__ import annotations

from typing import Any, Optional

from src.agent.operational.collector import (
    HealthMonitorContextCollector,
    OperationalContextCollectorProtocol,
)
from src.agent.router.state import RouterState


class OperationalStatusNode:
    def __init__(self, collector: Optional[OperationalContextCollectorProtocol] = None):
        self._collector = collector or HealthMonitorContextCollector(None)

    def __call__(self, state: RouterState) -> dict[str, Any]:
        context = self._collector.collect()
        return {"operational_context": context}
