from __future__ import annotations

from src.agent.runtime_debug.models import Evidence, RuntimeErrorEvent
from src.agent.runtime_debug.tools import RuntimeDebugToolbox


class ReconciliationPlaybook:
    name: str = "reconciliation_discrepancy"

    def matches(self, event: RuntimeErrorEvent) -> bool:
        msg = (event.message or "").lower()
        error_type = (event.error_type or "").lower()
        return (
                "reconciliation" in msg
                or "position_mismatch" in msg
                or "balance_mismatch" in msg
                or "orphan_order" in msg
                or "discrepancy" in msg
                or "reconciliation" in error_type
        )

    def investigate(self, event: RuntimeErrorEvent, toolbox: RuntimeDebugToolbox) -> list[Evidence]:
        evidence_list: list[Evidence] = []
        exchange = event.exchange or "UNKNOWN"
        asset = event.asset

        evidence_list.append(
            Evidence(
                title="Exchange Reconciliation Discrepancy",
                description=f"Reconciliation engine flagged state mismatch on {exchange} for {asset or 'account'}: {event.message}",
                source="reconciliation_engine",
                data={
                    "exchange": exchange,
                    "asset": asset,
                    "error_type": event.error_type,
                    "message": event.message,
                    "http_status": event.http_status,
                },
            )
        )

        recent_errors = toolbox.get_recent_errors(asset=asset, exchange=exchange, limit=10)
        evidence_list.append(
            Evidence(
                title="Telemetry Context",
                description=f"Found {len(recent_errors)} correlated error events across {exchange}/{asset}.",
                source="runtime_telemetry",
                data={"recent_error_count": len(recent_errors)},
            )
        )

        return evidence_list
