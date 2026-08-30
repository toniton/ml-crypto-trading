from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class OracleSummary:
    """The output of an Oracle analysis, expressed as a durable value object.

    The summary is the deterministic product of a single Oracle run and can be
    cached, persisted, or published as an event without re-invoking the LLM.
    """

    summary: str
    market_state: str
    trading_state: str
    risk_state: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str | None = None
    symbol: str | None = None
    correlation_id: str = field(default_factory=lambda: uuid4().hex)
    observations: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()
    model: str | None = None
    model_version: str | None = None

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "market_state": self.market_state,
            "trading_state": self.trading_state,
            "risk_state": self.risk_state,
            "generated_at": self.generated_at.isoformat(),
            "session_id": self.session_id,
            "symbol": self.symbol,
            "correlation_id": self.correlation_id,
            "observations": list(self.observations),
            "recommendations": list(self.recommendations),
            "model": self.model,
            "model_version": self.model_version,
        }
