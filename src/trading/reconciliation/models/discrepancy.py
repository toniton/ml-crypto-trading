from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class DiscrepancyType(str, Enum):
    BALANCE_MISMATCH = "BALANCE_MISMATCH"
    ORDER_STATUS_MISMATCH = "ORDER_STATUS_MISMATCH"
    ORPHAN_ORDER_DETECTED = "ORPHAN_ORDER_DETECTED"
    MISSING_FILL = "MISSING_FILL"
    POSITION_MISMATCH = "POSITION_MISMATCH"
    FEE_MISMATCH = "FEE_MISMATCH"
    UNTRACKED_TRANSFER = "UNTRACKED_TRANSFER"


class DiscrepancySeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Discrepancy:
    discrepancy_type: DiscrepancyType
    severity: DiscrepancySeverity
    exchange: str
    asset_or_currency: str
    local_value: Any
    exchange_value: Any
    difference: Optional[Decimal] = None
    action_taken: str = "NONE"
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def is_critical(self) -> bool:
        return self.severity == DiscrepancySeverity.CRITICAL

    @property
    def is_warning(self) -> bool:
        return self.severity == DiscrepancySeverity.WARNING

    def format_alert(self) -> str:
        diff_str = f"{self.difference:+}" if self.difference is not None else "N/A"
        return (
            f"\n{self.discrepancy_type.value}\n\n"
            f"Exchange:\n{self.exchange}\n\n"
            f"Asset/Currency:\n{self.asset_or_currency}\n\n"
            f"Local:\n{self.local_value}\n\n"
            f"Exchange:\n{self.exchange_value}\n\n"
            f"Difference:\n{diff_str}\n\n"
            f"Severity:\n{self.severity.value}\n\n"
            f"Action:\n{self.action_taken}\n"
        )
