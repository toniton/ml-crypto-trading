from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
import uuid

from src.agent.actions.models import ActionReason, AgentAction, AgentActionType
from src.agent.actions.service import AgentActionService
from src.core.hooks import (
    HookCatalog,
    HookContext,
    HookExecutionMode,
    HookManager,
    HookStage,
)
from src.core.interfaces.conversation_store import RESERVED_AGENT_SESSION_ID
from src.core.interfaces.event_bus import EventBus
from src.core.severity import Severity
from src.events.decision_models import (
    ActorType,
    AgentDecisionRecordedEvent,
    DecisionRecord,
    DecisionType,
    EntityRef,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin


@dataclass(frozen=True)
class CandidateOutcome:
    """Normalized performance metrics for a single experiment candidate."""

    candidate_id: str
    name: str
    total_trades: int
    net_pnl: float
    win_rate_pct: float
    profit_factor: float
    max_drawdown: float
    wf_oos_return_pct: Optional[float] = None
    wf_efficiency: Optional[float] = None
    wf_stability: Optional[str] = None


class ExperimentCompletionAgentHandler(ApplicationLoggingMixin):
    """Listens to experiment lifecycle hooks and posts agent summaries/decisions."""

    def __init__(
            self,
            event_bus: EventBus,
            action_service: Optional[AgentActionService] = None,
    ) -> None:
        self._event_bus = event_bus
        self._action_service = action_service or AgentActionService(event_bus=event_bus)

    def register(
            self,
            hook_manager: HookManager,
            priority: int = 100,
    ) -> str:
        """Subscribes this handler to terminal experiment.run hook stages."""
        return hook_manager.register(
            HookCatalog.EXPERIMENT_RUN,
            self.handle,
            stages=(HookStage.COMPLETED, HookStage.FAILED, HookStage.CANCELLED),
            priority=priority,
            mode=HookExecutionMode.ASYNC,
            name="agent_experiment_completion_handler",
        )

    def handle(self, context: HookContext) -> None:
        """Processes a terminal experiment hook and notifies the Agent Feed."""
        payload = context.payload
        experiment_id = str(payload.get("experiment_id") or context.source_id)
        ticker_symbol = str(payload.get("ticker_symbol") or "UNKNOWN")
        exp_name = str(payload.get("name") or experiment_id)

        if context.stage == HookStage.COMPLETED:
            self._handle_completed(
                context=context,
                experiment_id=experiment_id,
                ticker_symbol=ticker_symbol,
                exp_name=exp_name,
            )
            return

        status_label = "failed" if context.stage == HookStage.FAILED else "was cancelled"
        title = f"Experiment {status_label} — {ticker_symbol}"
        error_line = f"\n- **Error:** {context.error}" if context.error else ""
        content = (
            f"### {title}\n\n"
            f"Experiment `{exp_name}` (`{experiment_id}`) {status_label}.{error_line}\n\n"
            f"Review the experiment details on the Experiments page to inspect candidate logs."
        )
        self._record_decision(
            context=context,
            experiment_id=experiment_id,
            ticker_symbol=ticker_symbol,
            summary=title,
            rationale=f"Experiment {experiment_id} ended in status {context.stage.value}.",
            parameters={"status": context.stage.value, "error": context.error},
        )
        self._send_agent_message(
            title=title,
            content=content,
            ticker_symbol=ticker_symbol,
            experiment_id=experiment_id,
            severity=Severity.WARNING,
            correlation_id=context.correlation_id,
        )

    def _handle_completed(
            self,
            context: HookContext,
            experiment_id: str,
            ticker_symbol: str,
            exp_name: str,
    ) -> None:
        report = context.payload.get("report")
        outcomes = self._extract_outcomes(report if isinstance(report, dict) else {})
        baseline = next(
            (o for o in outcomes if o.candidate_id == "cand_current"),
            outcomes[0] if outcomes else None,
        )
        best = self._select_best_candidate(outcomes)

        title = f"Experiment completed — {ticker_symbol}"
        recommendation = self._build_recommendation(baseline, best)
        content = self._format_completed_markdown(
            title=title,
            exp_name=exp_name,
            experiment_id=experiment_id,
            outcomes=outcomes,
            recommendation=recommendation,
        )
        self._record_decision(
            context=context,
            experiment_id=experiment_id,
            ticker_symbol=ticker_symbol,
            summary=title,
            rationale=recommendation,
            parameters={
                "status": "COMPLETED",
                "candidates_evaluated": len(outcomes),
                "best_candidate_id": best.candidate_id if best is not None else None,
                "baseline_candidate_id": (
                    baseline.candidate_id if baseline is not None else None
                ),
            },
        )
        self._send_agent_message(
            title=title,
            content=content,
            ticker_symbol=ticker_symbol,
            experiment_id=experiment_id,
            severity=Severity.INFO,
            correlation_id=context.correlation_id,
        )

    def _send_agent_message(  # pylint: disable=too-many-arguments
            self,
            title: str,
            content: str,
            ticker_symbol: str,
            experiment_id: str,
            severity: Severity,
            correlation_id: Optional[str],
    ) -> None:
        action = AgentAction(
            type=AgentActionType.SEND_MESSAGE,
            title=title,
            description=content,
            conversation_id=RESERVED_AGENT_SESSION_ID,
            payload={
                "asset": ticker_symbol,
                "experiment_id": experiment_id,
                "blocks": [{"type": "markdown", "content": content}],
            },
            reason=ActionReason(
                trigger="EXPERIMENT_COMPLETED",
                evidence_ids=[experiment_id],
                related_entities=[ticker_symbol, experiment_id],
            ),
            severity=severity,
            correlation_id=correlation_id,
        )
        self._action_service.send_proactive_message(
            conversation_id=RESERVED_AGENT_SESSION_ID,
            message_id=f"exp_done_{experiment_id}_{uuid.uuid4().hex[:6]}",
            content=content,
            blocks=[{"type": "markdown", "content": content}],
            action=action,
            force=True,
        )

    def _record_decision(  # pylint: disable=too-many-arguments
            self,
            context: HookContext,
            experiment_id: str,
            ticker_symbol: str,
            summary: str,
            rationale: str,
            parameters: dict[str, Any],
    ) -> None:
        try:
            record = DecisionRecord(
                actor_type=ActorType.AGENT,
                actor_id="experiment_completion_handler",
                decision_type=DecisionType.INVESTIGATION_OUTCOME,
                summary=summary,
                rationale=rationale,
                evidence_ids=[experiment_id],
                entities=[
                    EntityRef(type="ASSET", id=ticker_symbol),
                    EntityRef(type="EXPERIMENT", id=experiment_id),
                ],
                parameters=parameters,
            )
            event = AgentDecisionRecordedEvent(decision=record)
            event.set_causality(
                correlation_id=context.correlation_id,
                causation_id=context.causation_id or experiment_id,
                asset=ticker_symbol,
                actor_type="AGENT",
                source="experiment_completion_handler",
            )
            self._event_bus.publish(event)
        except Exception:  # pylint: disable=broad-except
            self.app_logger.exception(
                "Failed to record decision for completed experiment %s",
                experiment_id,
            )

    @staticmethod
    def _extract_outcomes(report: dict[str, Any]) -> list[CandidateOutcome]:
        raw_candidates = report.get("candidates")
        if not isinstance(raw_candidates, dict):
            return []
        outcomes: list[CandidateOutcome] = []
        for cand_id, entry in raw_candidates.items():
            if not isinstance(entry, dict):
                continue
            bt = entry.get("backtest") if isinstance(entry.get("backtest"), dict) else entry
            wf = entry.get("walk_forward") if isinstance(entry.get("walk_forward"), dict) else None
            wf_oos: Optional[float] = None
            wf_wfe: Optional[float] = None
            wf_stability: Optional[str] = None
            if wf is not None:
                raw_oos = wf.get("aggregate_oos_return_pct")
                if raw_oos is None:
                    raw_oos = wf.get("out_of_sample_return_pct")
                if raw_oos is not None:
                    wf_oos = float(raw_oos)
                raw_wfe = wf.get("walk_forward_efficiency_ratio")
                if raw_wfe is None:
                    raw_wfe = wf.get("walk_forward_efficiency")
                if raw_wfe is not None:
                    wf_wfe = float(raw_wfe)
                if wf.get("stability_classification") is not None:
                    wf_stability = str(wf["stability_classification"])
            outcomes.append(
                CandidateOutcome(
                    candidate_id=str(cand_id),
                    name=str(entry.get("name") or cand_id),
                    total_trades=int(bt.get("total_trades") or bt.get("trades_count") or 0),
                    net_pnl=float(bt.get("net_pnl") or bt.get("total_pnl") or 0.0),
                    win_rate_pct=float(bt.get("win_rate_pct") or 0.0),
                    profit_factor=float(bt.get("profit_factor") or 0.0),
                    max_drawdown=float(bt.get("max_drawdown") or 0.0),
                    wf_oos_return_pct=wf_oos,
                    wf_efficiency=wf_wfe,
                    wf_stability=wf_stability,
                )
            )
        return outcomes

    @staticmethod
    def _select_best_candidate(
            outcomes: list[CandidateOutcome],
    ) -> Optional[CandidateOutcome]:
        if not outcomes:
            return None
        with_trades = [o for o in outcomes if o.total_trades > 0]
        pool = with_trades or outcomes
        return max(
            pool,
            key=lambda o: (o.net_pnl, o.profit_factor, o.win_rate_pct, o.total_trades),
        )

    @staticmethod
    def _build_recommendation(
            baseline: Optional[CandidateOutcome],
            best: Optional[CandidateOutcome],
    ) -> str:
        if best is None:
            return (
                "Experiment finished with no candidate metrics recorded. "
                "Inspect the experiment report for data coverage."
            )
        if best.total_trades == 0:
            return (
                "None of the tested candidates produced trades in the observed window. "
                "Consider widening the evaluation window or testing lower consensus thresholds."
            )
        if baseline is not None and best.candidate_id == baseline.candidate_id:
            return (
                f"Baseline `{baseline.name}` remained the strongest configuration "
                f"({baseline.total_trades} trades, net PnL {baseline.net_pnl:+.2f}). "
                f"No immediate configuration change is recommended."
            )
        if baseline is not None and baseline.total_trades == 0:
            wf_note = (
                f" Walk-forward OOS return {best.wf_oos_return_pct:+.2f}%"
                f"{f' ({best.wf_stability})' if best.wf_stability else ''}."
                if best.wf_oos_return_pct is not None
                else " Review in Experiments and run walk-forward validation before promoting."
            )
            return (
                f"Candidate `{best.name}` broke signal starvation with {best.total_trades} "
                f"trade(s) (net PnL {best.net_pnl:+.2f}, win rate {best.win_rate_pct:.1f}%) "
                f"vs 0 baseline trades.{wf_note}"
            )
        wf_note = (
            f" Walk-forward OOS return {best.wf_oos_return_pct:+.2f}%"
            f"{f' ({best.wf_stability})' if best.wf_stability else ''}. "
            f"Review the full report before promotion."
            if best.wf_oos_return_pct is not None
            else " Review the full report and validate with walk-forward testing before promotion."
        )
        return (
            f"Candidate `{best.name}` outperformed baseline with {best.total_trades} trade(s) "
            f"(net PnL {best.net_pnl:+.2f}, win rate {best.win_rate_pct:.1f}%, "
            f"PF {best.profit_factor:.2f}).{wf_note}"
        )

    @staticmethod
    def _format_completed_markdown(
            title: str,
            exp_name: str,
            experiment_id: str,
            outcomes: list[CandidateOutcome],
            recommendation: str,
    ) -> str:
        lines = [
            f"### {title}",
            "",
            f"Experiment **{exp_name}** (`{experiment_id}`) finished.",
            "",
            f"**Summary:** {recommendation}",
        ]
        if outcomes:
            has_wf = any(o.wf_oos_return_pct is not None for o in outcomes)
            if has_wf:
                lines.extend(
                    [
                        "",
                        "| Candidate | Trades | Net PnL | Win Rate | Profit Factor | WF OOS | Stability |",
                        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
                    ]
                )
                for item in outcomes:
                    wf_oos_str = (
                        f"{item.wf_oos_return_pct:+.2f}%"
                        if item.wf_oos_return_pct is not None
                        else "—"
                    )
                    stability_str = item.wf_stability or "—"
                    lines.append(
                        f"| {item.name} | {item.total_trades} | "
                        f"{item.net_pnl:+.2f} | {item.win_rate_pct:.1f}% | "
                        f"{item.profit_factor:.2f} | {wf_oos_str} | {stability_str} |"
                    )
            else:
                lines.extend(
                    [
                        "",
                        "| Candidate | Trades | Net PnL | Win Rate | Profit Factor |",
                        "| --- | ---: | ---: | ---: | ---: |",
                    ]
                )
                for item in outcomes:
                    lines.append(
                        f"| {item.name} | {item.total_trades} | "
                        f"{item.net_pnl:+.2f} | {item.win_rate_pct:.1f}% | "
                        f"{item.profit_factor:.2f} |"
                    )
        return "\n".join(lines)
