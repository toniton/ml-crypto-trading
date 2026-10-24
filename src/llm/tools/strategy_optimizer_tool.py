from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from api.interfaces.evidence_proposal import EvidenceBasedProposal
from api.interfaces.order import Order
from api.interfaces.trade import Trade
from src.agent.configuration.configuration_service import ConfigurationService
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_evidence_proposal_repository import (
    PostgresEvidenceProposalRepository,
)
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.database.repositories.providers.postgres_trade_repository import PostgresTradeRepository
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.proposals.optimizer_proposal_builder import OptimizerProposalBuilder
from src.server.services.asset_performance_service import AssetPerformanceService
from src.trading.analytics.strategy_optimizer import (
    BaselineComparisonResult,
    StrategyOptimizer,
)
from src.vcs.domain.diff import ConfigChange, ConfigurationProposal


class StrategyOptimizerInput(BaseModel):
    action: str = Field(
        default="calibrate",
        description="Optimization action: 'calibrate', 'windows', 'redundancy', 'proposal', or 'compare'.",
    )
    ticker_symbol: Optional[str] = Field(
        default=None,
        description="Ticker symbol (e.g. 'BTC_USD') to optimize.",
    )
    lookback_days: int = Field(
        default=30,
        description="Number of days of trade history to analyze (default: 30).",
    )
    timezone: str = Field(
        default="UTC",
        description="Target timezone for schedule optimization (default: 'UTC').",
    )


class StrategyOptimizerTool(BaseTool, ApplicationLoggingMixin):
    name: str = "strategy_optimizer"
    description: str = (
        "Empirically optimizes strategy weights, discovers profitable trading windows, "
        "detects redundant co-voting strategies, and generates configuration proposals."
    )
    args_schema: Type[BaseModel] = StrategyOptimizerInput

    database_manager: DatabaseManager
    configuration_service: ConfigurationService

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(
            self,
            database_manager: DatabaseManager,
            configuration_service: ConfigurationService,
    ):
        self._audit_warning: Optional[str] = None
        super().__init__(
            database_manager=database_manager,
            configuration_service=configuration_service,
        )

    def _run(  # pylint: disable=arguments-differ,redefined-outer-name
            self,
            action: str = "calibrate",
            ticker_symbol: Optional[str] = None,
            lookback_days: int = 30,
            timezone: str = "UTC",
    ) -> str:
        self.app_logger.info(
            f"Strategy optimizer tool called (action={action}, symbol={ticker_symbol}, lookback={lookback_days}d)"
        )
        norm_action = action.strip().lower()

        asset_config: Optional[dict[str, Any]] = None
        base_commit_hash: Optional[str] = None
        if norm_action in ("calibrate", "proposal", "compare"):
            asset_config, base_commit_hash, err = self._get_asset_config_snapshot(ticker_symbol)
            if err is not None or asset_config is None:
                return err or "Error loading asset configuration."

        trades = self._gather_trades(ticker_symbol=ticker_symbol, lookback_days=lookback_days)
        if not trades:
            return "No historical trades found for the specified asset/period to perform optimization."

        if norm_action == "windows":
            result = self._run_windows(trades, ticker_symbol, timezone)
        elif norm_action == "redundancy":
            result = self._run_redundancy(trades)
        elif norm_action == "proposal":
            result = self._run_proposal(
                trades,
                ticker_symbol,
                timezone,
                asset_config,
                base_commit_hash=base_commit_hash,
            )
        elif norm_action == "compare":
            result = self._run_compare(trades, ticker_symbol, asset_config)
        else:
            result = self._run_calibrate(trades, ticker_symbol, asset_config)

        if self._audit_warning:
            return f"{result}\n\n{self._audit_warning}"
        return result

    def _get_asset_config_snapshot(
            self, ticker_symbol: Optional[str]
    ) -> tuple[Optional[dict[str, Any]], Optional[str], Optional[str]]:
        if not ticker_symbol:
            return None, None, "Error: 'ticker_symbol' is required for strategy calibration and proposal generation."

        snapshot_res = self.configuration_service.get_asset_config_snapshot(ticker_symbol)
        if isinstance(snapshot_res, tuple) and len(snapshot_res) == 2:
            asset_config, commit_hash = snapshot_res
        else:
            asset_config = self.configuration_service.get_asset_config(ticker_symbol)
            commit_hash = None

        if asset_config is None:
            return None, None, f"Error: Asset '{ticker_symbol}' is not configured in the active configuration."

        return asset_config, commit_hash, None

    def _get_asset_config(self, ticker_symbol: Optional[str]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        cfg, _, err = self._get_asset_config_snapshot(ticker_symbol)
        return cfg, err

    def _get_base_commit_hash(self) -> Optional[str]:
        return self.configuration_service.get_head_commit_hash()

    @staticmethod
    def _run_windows(trades: list[Trade], ticker_symbol: Optional[str], target_tz: str) -> str:
        windows = StrategyOptimizer.optimize_trading_windows(trades, timezone_str=target_tz)
        if not windows:
            return f"No distinct profitable hourly windows discovered for {ticker_symbol or 'all assets'}."
        lines = [f"### 🕒 Recommended Trading Windows ({target_tz})\n"]
        for i, w in enumerate(windows, 1):
            days_str = ", ".join(d.name.title() for d in w.days)
            lines.append(
                f"**Window #{i}**: {days_str} from {w.start_time.strftime('%H:%M')} to {w.end_time.strftime('%H:%M')}"
            )
        return "\n".join(lines)

    @staticmethod
    def _run_redundancy(trades: list[Trade]) -> str:
        redundancies = StrategyOptimizer.detect_strategy_redundancies(trades)
        if not redundancies:
            return "No high-redundancy strategy pairs detected (all co-voting agreement rates < 85%)."
        lines = ["### ⚠️ Strategy Redundancy Analysis\n"]
        for r in redundancies:
            sample_str = f" across {r.aligned_decisions} decision(s)" if r.aligned_decisions > 0 else ""
            lines.append(
                f"- **{r.strategy_a} & {r.strategy_b}**: {r.agreement_rate_pct}% agreement{sample_str} "
                f"({r.co_sponsored_trades} co-sponsored trade(s)). {r.recommendation}"
            )
        return "\n".join(lines)

    def _persist_evidence_proposal(self, proposal: EvidenceBasedProposal) -> None:
        try:
            with self.database_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresEvidenceProposalRepository)
                if isinstance(repo, PostgresEvidenceProposalRepository):
                    repo.save(proposal)
                    uow.commit()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.app_logger.warning(f"Could not persist optimizer evidence proposal: {exc}")

    @staticmethod
    def _format_proposal_changes(changes: list[ConfigChange]) -> str:
        if not changes:
            return "_No changes proposed (current weights and schedules are already optimal)._"
        return "\n".join(
            f"- `{c.path}`: `{c.old_value}` -> `{c.new_value}` ({c.reason})" for c in changes
        )

    @classmethod
    def _format_proposal_output(
            cls,
            sym: str,
            prop: ConfigurationProposal,
            evidence_prop: EvidenceBasedProposal,
    ) -> str:
        changes_list = list(prop.changes or [])
        changes_str = cls._format_proposal_changes(changes_list)
        all_risks = list(prop.risks or [])
        for lim in evidence_prop.limitations:
            if lim not in all_risks:
                all_risks.append(lim)
        risks_str = "\n".join(f"- {r}" for r in all_risks)
        plan_str = "\n".join(f"- {step}" for step in evidence_prop.validation_plan)
        commit_line = f"**Base Commit**: `{prop.base_commit_hash}`\n\n" if prop.base_commit_hash else ""

        return (
            f"### 📋 Optimization Proposal Generated for {sym}\n\n"
            f"**Proposal ID**: `{evidence_prop.id}` | "
            f"**Evidence Status**: `{evidence_prop.evidence_status.value}` | "
            f"**Recommendation**: `{evidence_prop.recommendation.value}`\n\n"
            f"**Summary**: {prop.summary}\n\n"
            f"{commit_line}"
            f"**Expected Effect**: {prop.expected_effect}\n\n"
            f"**Proposed Changes ({len(changes_list)})**:\n"
            f"{changes_str}\n\n"
            f"**Risks & Limitations**:\n"
            f"{risks_str}\n\n"
            f"**Validation Plan**:\n"
            f"{plan_str}"
        )

    def _run_proposal(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            trades: list[Trade],
            ticker_symbol: Optional[str],
            target_tz: str,
            asset_config: dict[str, Any],
            base_commit_hash: Optional[str] = None,
    ) -> str:
        sym = ticker_symbol.strip() if ticker_symbol else "PORTFOLIO"
        prop, evidence_prop = OptimizerProposalBuilder.build_evidence_proposal(
            sym,
            asset_config,
            trades,
            timezone_str=target_tz,
            base_commit_hash=base_commit_hash,
        )
        self._persist_evidence_proposal(evidence_prop)
        return self._format_proposal_output(sym, prop, evidence_prop)

    @staticmethod
    def _extract_active_weights(
            asset_config: dict[str, Any], ticker_symbol: Optional[str]
    ) -> tuple[Optional[dict[str, float]], Optional[str]]:
        strategies = asset_config.get("strategies", [])
        if not strategies:
            return None, f"Error: No strategies configured for asset '{ticker_symbol}'."
        active_weights = {
            strat.get("name"): float(strat.get("weight", 1.0))
            for strat in strategies
            if strat.get("name") and strat.get("enabled", True)
        }
        if not active_weights:
            return None, f"Error: No active/enabled strategies configured for asset '{ticker_symbol}'."
        return active_weights, None

    @staticmethod
    def _format_baseline_comparison(eval_res: BaselineComparisonResult) -> list[str]:
        b = eval_res.baseline_metrics
        p = eval_res.proposed_metrics
        e = eval_res.equal_weight_metrics
        return [
            "### 📊 Out-of-Sample Walk-Forward Baseline Comparison (Preliminary Attribution Diagnostic)",
            (
                f"- **Sample Split**: {eval_res.in_sample_trades_count} in-sample (calibration) / "
                f"{eval_res.out_of_sample_trades_count} out-of-sample (evaluation) trades"
            ),
            (
                f"- **Unchanged Baseline**: Net P&L = {b.net_pnl:.2f}, "
                f"PF = {b.profit_factor:.2f}, Win Rate = {b.win_rate_pct:.1f}%, "
                f"Max Drawdown = {b.max_drawdown:.2f}"
            ),
            (
                f"- **Proposed Calibrated**: Net P&L = {p.net_pnl:.2f}, "
                f"PF = {p.profit_factor:.2f}, Win Rate = {p.win_rate_pct:.1f}%, "
                f"Max Drawdown = {p.max_drawdown:.2f}"
            ),
            (
                f"- **Equal-Weight Benchmark**: Net P&L = {e.net_pnl:.2f}, "
                f"PF = {e.profit_factor:.2f}, Win Rate = {e.win_rate_pct:.1f}%, "
                f"Max Drawdown = {e.max_drawdown:.2f}"
            ),
            f"- **Net P&L Delta vs Baseline**: {eval_res.pnl_delta:+.2f} ({eval_res.pnl_improvement_pct:+.1f}%)",
            f"- **Max Drawdown Delta vs Baseline**: {eval_res.drawdown_delta:+.2f}",
            f"- **Verdict**: {eval_res.verdict}",
            (
                "- **Multi-Fold Walk-Forward Validation**: Run the `walk_forward` tool "
                "for full chronological multi-fold out-of-sample simulation."
            ),
        ]

    @classmethod
    def _run_calibrate(
            cls,
            trades: list[Trade],
            ticker_symbol: Optional[str],
            asset_config: dict[str, Any],
    ) -> str:
        active_weights, err = cls._extract_active_weights(asset_config, ticker_symbol)
        if err is not None or active_weights is None:
            return err or "Error extracting strategy weights."

        if len(trades) >= 4:
            in_sample, _ = StrategyOptimizer._split_trades_chronologically(trades, 0.7)  # pylint: disable=protected-access
        else:
            in_sample = trades

        recommendations = StrategyOptimizer.calibrate_strategy_weights(in_sample, active_weights)
        lines = [
            f"### ⚖️ Strategy Weight Calibration Recommendations for {ticker_symbol}\n"
            f"*(Empirical heuristic fitted on in-sample trade attribution; full walk-forward validation required)*\n"
        ]
        for rec in recommendations:
            metrics_desc = (
                f"(Evidence: {rec.evidence_status}, Confidence: {rec.confidence_level}, "
                f"Win Rate: {rec.win_rate_pct:.1f}% ± {rec.sample_margin_of_error_pct:.1f}%, "
                f"PF: {rec.profit_factor:.2f}, Trades: {rec.total_trades}, "
                f"Windows: {rec.independent_windows})"
            )
            lines.append(
                f"- **{rec.strategy_name}**: Current={rec.current_weight:.2f} -> "
                f"**Recommended={rec.recommended_weight:.2f}** {metrics_desc}\n"
                f"  _{rec.rationale}_"
            )

        proposed_w = {rec.strategy_name: rec.recommended_weight for rec in recommendations}
        baseline_eval = StrategyOptimizer.evaluate_split_sample_baseline(trades, active_weights, proposed_w)
        if baseline_eval is not None:
            lines.append("")
            lines.extend(cls._format_baseline_comparison(baseline_eval))

        return "\n".join(lines)

    @classmethod
    def _run_compare(
            cls,
            trades: list[Trade],
            ticker_symbol: Optional[str],
            asset_config: dict[str, Any],
    ) -> str:
        active_weights, err = cls._extract_active_weights(asset_config, ticker_symbol)
        if err is not None or active_weights is None:
            return err or "Error extracting strategy weights."

        baseline_eval = StrategyOptimizer.evaluate_split_sample_baseline(
            trades, active_weights, proposed_weights=None
        )
        if baseline_eval is None:
            return (
                f"Insufficient trade history ({len(trades)} trades) to perform split-sample "
                f"walk-forward comparison for {ticker_symbol}."
            )

        lines = [
            f"### 📊 Walk-Forward Baseline Comparison for {ticker_symbol}\n"
            f"*(Out-of-sample evaluation comparing in-sample calibrated weights against the unchanged baseline)*\n"
        ]
        lines.extend(cls._format_baseline_comparison(baseline_eval))
        return "\n".join(lines)

    def _gather_trades(self, ticker_symbol: Optional[str], lookback_days: int) -> list[Trade]:
        return self._fetch_db_trades(ticker_symbol, lookback_days)

    @staticmethod
    def _extract_and_audit_orders(
            orders: list[Order],
            symbols: list[str],
            target_start: datetime,
    ) -> tuple[list[Trade], int]:
        all_trades: list[Trade] = []
        total_unmatched = 0
        for symbol in symbols:
            sym_orders = [o for o in orders if o.ticker_symbol == symbol]
            extraction = AssetPerformanceService.extract_trades_with_audit(symbol, sym_orders)
            valid_trades = [t for t in extraction.trades if t.exit_timestamp >= target_start.timestamp()]
            all_trades.extend(valid_trades)
            total_unmatched += extraction.unmatched_exit_orders
        return all_trades, total_unmatched

    def _fetch_db_trades(self, ticker_symbol: Optional[str], lookback_days: int) -> list[Trade]:
        now = datetime.now(timezone.utc)
        target_start = now - timedelta(days=max(1, lookback_days))
        fetch_start = now - timedelta(days=int(max(1, lookback_days) * 1.5) + 1)
        self._audit_warning = None

        with self.database_manager.get_unit_of_work() as uow:
            sym = ticker_symbol.strip() if ticker_symbol else None
            trade_repo = uow.get_repository(PostgresTradeRepository)
            persisted_trades = trade_repo.get_by_exit_range(sym, start=target_start, end=now)
            if persisted_trades:
                return persisted_trades

            order_repo = uow.get_repository(PostgresOrderRepository)
            if ticker_symbol:
                orders = order_repo.get_completed_by_ticker_and_executed_range(
                    ticker_symbol=ticker_symbol.strip(),
                    start=fetch_start,
                    end=now,
                )
                symbols = [ticker_symbol.strip()]
            else:
                orders = order_repo.get_completed_by_executed_range(start=fetch_start, end=now)
                symbols = list({o.ticker_symbol for o in orders})

            all_trades, total_unmatched = self._extract_and_audit_orders(orders, symbols, target_start)

            if total_unmatched > 0:
                self._audit_warning = (
                    f"⚠️ Warning: Incomplete historical lookback detected "
                    f"({total_unmatched} closing order(s) without matching entry lots "
                    f"prior to the lookback window; metrics may reflect partial position data)."
                )

            return all_trades
