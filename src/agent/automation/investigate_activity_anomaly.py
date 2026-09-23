from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from src.agent.monitoring.activity_state import ActivityStateProvider, AssetActivityState
from src.backtest.analysis.drift_detector import BacktestDriftDetector, DriftReport
from src.events.agent_events import TradingActivityAnomalyDetectedEvent
from src.logging.application_logging_mixin import ApplicationLoggingMixin


@dataclass
class AnomalyDecision:
    kind: Literal["message", "diagnostic", "proposal"]
    asset: str
    content: str
    blocks: list[dict] = field(default_factory=list)
    proposed_change: Optional[dict] = None


class InvestigateActivityAnomaly(ApplicationLoggingMixin):
    def __init__(
            self,
            activity_provider: ActivityStateProvider,
            drift_detector: Optional[BacktestDriftDetector] = None,
    ):
        self._activity_provider = activity_provider
        self._drift_detector = drift_detector

    def investigate(self, event: TradingActivityAnomalyDetectedEvent) -> AnomalyDecision:
        state = self._activity_provider.state_for(event.asset)
        drift = self._detect_drift(event.asset)

        if event.anomaly_kind in ("NO_MARKET_DATA", "NO_STRATEGY_ACTIVITY"):
            return self._message_decision(
                event,
                state,
                drift,
                "Connectivity or data feed problem",
                "No market data / strategy activity received within the expected interval. "
                "Check the market data feed, scheduler, and exchange connectivity.",
            )

        if event.anomaly_kind == "NO_SIGNALS":
            return self._message_decision(
                event,
                state,
                drift,
                "Strategy behaviour",
                "The strategy is evaluating but producing no consensus signals within the "
                "expected interval. Market conditions may simply be outside the strategy's "
                "thresholds.",
            )

        if event.anomaly_kind == "NO_EXECUTIONS":
            return self._message_decision(
                event,
                state,
                drift,
                "Exchange or order problem",
                "Orders are being submitted but none are executing. Check exchange "
                "connectivity, order precision, and outstanding order state.",
            )

        # NO_ORDERS with recent signals strongly suggests risk/configuration gating.
        return self._proposal_decision(event, state, drift)

    def _detect_drift(self, ticker_symbol: str) -> Optional[DriftReport]:
        if self._drift_detector is None:
            return None
        try:
            return self._drift_detector.detect(ticker_symbol)
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.warning(f"Drift detection failed for {ticker_symbol}: {exc}")
            return None

    def _message_decision(
            self,
            event: TradingActivityAnomalyDetectedEvent,
            state: Optional[AssetActivityState],
            drift: Optional[DriftReport],
            title: str,
            body: str,
    ) -> AnomalyDecision:
        content, blocks = self._build_diagnostic(event, state, drift, title, body)
        return AnomalyDecision(kind="diagnostic", asset=event.asset, content=content, blocks=blocks)

    def _proposal_decision(
            self,
            event: TradingActivityAnomalyDetectedEvent,
            state: Optional[AssetActivityState],
            drift: Optional[DriftReport],
    ) -> AnomalyDecision:
        title = "Risk or configuration gating"
        body = (
            "The strategy has generated signals but no orders are being submitted. This "
            "suggests a risk guard or configuration change is blocking trading. Proposing "
            "to pause the asset until reviewed."
        )
        content, blocks = self._build_diagnostic(event, state, drift, title, body)
        proposed_change = {
            "changes": [
                {
                    "path": f"assets.{event.asset}.enabled",
                    "old_value": True,
                    "new_value": False,
                    "reason": f"Trading starvation detected for {event.asset} "
                              f"(anomaly={event.anomaly_kind}); pausing until reviewed.",
                }
            ],
            "risks": ["Asset will not trade until re-enabled."],
            "expected_effect": f"Pause trading for {event.asset} until activity resumes.",
        }
        return AnomalyDecision(
            kind="proposal",
            asset=event.asset,
            content=content,
            blocks=blocks,
            proposed_change=proposed_change,
        )

    @staticmethod
    def _build_diagnostic(
            event: TradingActivityAnomalyDetectedEvent,
            state: Optional[AssetActivityState],
            drift: Optional[DriftReport],
            title: str,
            body: str,
    ) -> tuple[str, list[dict]]:
        lines = [
            f"### {title} — {event.asset}",
            "",
            body,
            "",
            f"- **Anomaly kind:** `{event.anomaly_kind}`",
            f"- **Threshold:** {event.threshold:.0f}s",
        ]
        if state is not None:
            lines.append(f"- **Last market data:** {_fmt(state.last_market_data_at)}")
            lines.append(f"- **Last evaluation:** {_fmt(state.last_evaluation_at)}")
            lines.append(f"- **Last signal:** {_fmt(state.last_signal_at)}")
            lines.append(f"- **Last order:** {_fmt(state.last_order_at)}")
            lines.append(f"- **Last execution:** {_fmt(state.last_execution_at)}")
        if drift is not None:
            lines.append("")
            lines.append("**Drift vs backtest replay:**")
            lines.append(f"- Fill count drift: {drift.fill_count_drift}")
            lines.append(f"- Quantity drift: {drift.quantity_drift}")
            lines.append(f"- Drifted: {drift.drifted}")
        content = "\n".join(lines)
        blocks: list[dict] = [{"type": "markdown", "content": content}]
        return content, blocks


def _fmt(timestamp: Optional[float]) -> str:
    if timestamp is None:
        return "never"
    elapsed = max(0.0, time.time() - timestamp)
    if elapsed < 60:
        return f"{elapsed:.0f}s ago"
    if elapsed < 3600:
        return f"{elapsed / 60:.1f}m ago"
    return f"{elapsed / 3600:.1f}h ago"