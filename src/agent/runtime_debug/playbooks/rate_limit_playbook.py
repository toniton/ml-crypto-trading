from __future__ import annotations

from src.agent.runtime_debug.models import Evidence, RuntimeErrorEvent
from src.agent.runtime_debug.tools import RuntimeDebugToolbox


class RateLimitPlaybook:
    name: str = "exchange_rate_limit"

    def matches(self, event: RuntimeErrorEvent) -> bool:
        msg = (event.message or "").lower()
        return event.http_status == 429 or "rate limit" in msg or "too many requests" in msg

    def investigate(self, event: RuntimeErrorEvent, toolbox: RuntimeDebugToolbox) -> list[Evidence]:
        evidence_list: list[Evidence] = []
        exchange = event.exchange or "UNKNOWN"
        asset = event.asset

        evidence_list.append(
            Evidence(
                title="HTTP 429 Rate Limit Exceeded",
                description=f"Exchange {exchange} responded with HTTP 429 Too Many Requests.",
                source="exchange_http_response",
                data={
                    "http_status": 429,
                    "exchange": exchange,
                    "asset": asset,
                },
            )
        )

        recent_errors = toolbox.get_recent_errors(asset=asset, exchange=exchange, limit=10)
        evidence_list.append(
            Evidence(
                title="Recent Error Frequency",
                description=f"Detected {len(recent_errors)} recent error events for {exchange}/{asset}.",
                source="runtime_telemetry",
                data={"recent_error_count": len(recent_errors)},
            )
        )

        return evidence_list
