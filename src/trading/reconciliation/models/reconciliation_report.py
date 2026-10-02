from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List

from .discrepancy import Discrepancy


@dataclass
class ReconciliationReport:
    cycle_id: str
    exchange: str
    started_at: float = field(default_factory=time.time)
    finished_at: float = field(default_factory=time.time)
    discrepancies: List[Discrepancy] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        return max(0.0, (self.finished_at - self.started_at) * 1000)

    @property
    def total_count(self) -> int:
        return len(self.discrepancies)

    @property
    def critical_discrepancies(self) -> List[Discrepancy]:
        return [d for d in self.discrepancies if d.is_critical]

    @property
    def warning_discrepancies(self) -> List[Discrepancy]:
        return [d for d in self.discrepancies if d.is_warning]

    @property
    def has_critical(self) -> bool:
        return any(d.is_critical for d in self.discrepancies)

    @property
    def actions_taken(self) -> List[str]:
        return [d.action_taken for d in self.discrepancies if d.action_taken != "NONE"]
