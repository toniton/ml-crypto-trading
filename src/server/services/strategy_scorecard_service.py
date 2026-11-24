from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal, Optional
import uuid

from api.interfaces.scorecard import (
    GateCheckSummary,
    GateSummary,
    LifecycleProgress,
    LifecycleStage,
    RegimePerformanceSlice,
    ScorecardSnapshotRecord,
    ScorecardSnapshotSummary,
    StageMetrics,
    StrategyAttributionSlice,
    StrategyScorecardResponse,
    StrategyScorecardSummary,
)
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_backtest_repository import (
    PostgresBacktestRepository,
)
from src.database.repositories.providers.postgres_experiment_repository import (
    PostgresExperimentRepository,
)
from src.database.repositories.providers.postgres_scorecard_snapshot_repository import (
    PostgresScorecardSnapshotRepository,
)
from src.server.services.asset_performance_service import (
    AssetPerformanceResponse,
    AssetPerformanceService,
)
from src.server.services.configuration_service import ConfigurationService
from src.server.services.drift_application_service import (
    DriftApplicationService,
    extract_quote_currency,
)
from src.server.services.experiment_application_service import (
    ExperimentApplicationService,
)
from src.server.services.simulation_orchestrator import SimulationOrchestrator
from src.server.services.simulation_report_service import SimulationReportService
from src.server.services.walk_forward_application_service import (
    WalkForwardApplicationService,
)
from src.vcs.application.service import VCSService

DEFAULT_LIVE_LOOKBACK_DAYS = 30
MAX_LIST_SCAN = 50


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(str(value).replace("+", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    parsed = _as_float(value)
    return int(parsed) if parsed is not None else None


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _nested_get(data: Optional[dict[str, Any]], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _commit_matches(candidate: Optional[str], target: Optional[str]) -> bool:
    if not target:
        return True
    if not candidate:
        return False
    cand = candidate.strip()
    tgt = target.strip()
    return (
        cand == tgt
        or (len(tgt) >= 7 and cand.startswith(tgt))
        or (len(cand) >= 7 and tgt.startswith(cand))
    )


class StrategyScorecardService:
    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            db_manager: DatabaseManager,
            vcs_service: VCSService,
            walk_forward_service: WalkForwardApplicationService,
            simulation_orchestrator: SimulationOrchestrator,
            simulation_report_service: SimulationReportService,
            experiment_service: ExperimentApplicationService,
            asset_performance_service: AssetPerformanceService,
            drift_service: DriftApplicationService,
            configuration_service: Optional[ConfigurationService] = None,
            venue: str = "default",
    ) -> None:
        self._db_manager = db_manager
        self._vcs = vcs_service
        self._walk_forward_service = walk_forward_service
        self._simulation_orchestrator = simulation_orchestrator
        self._simulation_report_service = simulation_report_service
        self._experiment_service = experiment_service
        self._asset_performance_service = asset_performance_service
        self._drift_service = drift_service
        self._configuration_service = configuration_service
        self._venue = venue
        self._fallback_snapshots: dict[str, ScorecardSnapshotRecord] = {}

    def list_scorecards(
            self,
            branch: str = "main",
    ) -> list[StrategyScorecardSummary]:
        symbols = self._discover_symbols()
        summaries: list[StrategyScorecardSummary] = []
        for symbol in symbols:
            card = self.get_scorecard(symbol=symbol, branch=branch)
            stage_map = {s.stage: s for s in card.stages}
            live = stage_map.get("live")
            oos = stage_map.get("walk_forward_oos")
            backtest = stage_map.get("backtest")
            max_dd = (
                (oos.max_drawdown_pct if oos and oos.max_drawdown_pct is not None else None)
                or (backtest.max_drawdown_pct if backtest else None)
            )
            summaries.append(
                StrategyScorecardSummary(
                    symbol=card.symbol,
                    venue=card.venue,
                    quote_currency=card.quote_currency,
                    branch=card.branch,
                    commit_hash=card.commit_hash,
                    current_stage=card.lifecycle.current_stage,
                    live_return_pct=live.return_pct if live else None,
                    oos_return_pct=oos.return_pct if oos else None,
                    backtest_return_pct=backtest.return_pct if backtest else None,
                    max_drawdown_pct=max_dd,
                    drifted=card.latest_drift.drifted if card.latest_drift else None,
                    updated_at=card.generated_at,
                )
            )
        return summaries

    def get_scorecard(
            self,
            symbol: str,
            commit_hash: Optional[str] = None,
            branch: str = "main",
    ) -> StrategyScorecardResponse:
        resolved_commit, commit_message = self._resolve_commit(commit_hash, branch)
        quote_currency = extract_quote_currency(symbol)
        strict_commit = commit_hash.strip() if commit_hash else None

        backtest_stage = self._load_backtest_stage(symbol, strict_commit)
        wf_is_stage, wf_oos_stage, regimes = self._load_walk_forward_stages(symbol, strict_commit)
        sim_stage, active_sim_id, gate_b = self._load_simulation_stage(symbol, strict_commit)
        live_stage, attribution = self._load_live_stage(symbol)
        active_experiment_id, gate_a = self._load_experiment_gate(symbol)
        latest_drift = self._drift_service.get_snapshot(symbol, commit_hash=strict_commit or resolved_commit)
        if latest_drift is None:
            latest_drift = self._load_latest_persisted_drift(symbol, strict_commit)

        stages = [backtest_stage, wf_is_stage, wf_oos_stage, sim_stage, live_stage]
        lifecycle = self._build_lifecycle_progress(
            stages=stages,
            gate_a=gate_a,
            gate_b=gate_b,
            active_experiment_id=active_experiment_id,
            active_simulation_id=active_sim_id,
        )

        return StrategyScorecardResponse(
            symbol=symbol,
            venue=self._venue,
            quote_currency=quote_currency,
            branch=branch,
            commit_hash=resolved_commit,
            commit_message=commit_message,
            generated_at=datetime.now(timezone.utc).isoformat(),
            lifecycle=lifecycle,
            stages=stages,
            regimes=regimes,
            attribution=attribution,
            latest_drift=latest_drift,
        )

    def save_snapshot(
            self,
            symbol: str,
            trigger: Literal["manual", "drift_run"] = "manual",
            commit_hash: Optional[str] = None,
            branch: str = "main",
    ) -> ScorecardSnapshotRecord:
        scorecard = self.get_scorecard(symbol=symbol, commit_hash=commit_hash, branch=branch)
        snapshot_id = f"sc_{uuid.uuid4().hex[:12]}"
        record = ScorecardSnapshotRecord(
            snapshot_id=snapshot_id,
            trigger=trigger,
            created_at=datetime.now(timezone.utc).isoformat(),
            scorecard=scorecard,
        )
        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresScorecardSnapshotRepository)
                repo.save_snapshot(record)
        except Exception:  # pylint: disable=broad-except
            self._fallback_snapshots[snapshot_id] = record
        return record

    def get_snapshot(self, snapshot_id: str) -> Optional[ScorecardSnapshotRecord]:
        if snapshot_id in self._fallback_snapshots:
            return self._fallback_snapshots[snapshot_id]
        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresScorecardSnapshotRepository)
                return repo.get_snapshot(snapshot_id)
        except Exception:  # pylint: disable=broad-except
            return None

    def _load_latest_persisted_drift(
            self,
            symbol: str,
            commit_hash: Optional[str] = None,
    ):
        summaries = self.list_snapshots(symbol=symbol, limit=20)
        for summary in summaries:
            if commit_hash and not _commit_matches(summary.commit_hash, commit_hash):
                continue
            record = self.get_snapshot(summary.snapshot_id)
            if record and record.scorecard.latest_drift is not None:
                return record.scorecard.latest_drift
        return None

    def list_snapshots(
            self,
            symbol: Optional[str] = None,
            limit: int = MAX_LIST_SCAN,
    ) -> list[ScorecardSnapshotSummary]:
        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresScorecardSnapshotRepository)
                return repo.list_snapshots(symbol=symbol, limit=limit)
        except Exception:  # pylint: disable=broad-except
            records = list(self._fallback_snapshots.values())
            if symbol:
                records = [r for r in records if r.scorecard.symbol == symbol]
            records.sort(key=lambda r: r.created_at, reverse=True)
            return [self._to_snapshot_summary(r) for r in records[:limit]]

    @staticmethod
    def _to_snapshot_summary(record: ScorecardSnapshotRecord) -> ScorecardSnapshotSummary:
        card = record.scorecard
        stage_map = {s.stage: s for s in card.stages}
        live = stage_map.get("live")
        oos = stage_map.get("walk_forward_oos")
        backtest = stage_map.get("backtest")
        max_dd = (
            (oos.max_drawdown_pct if oos and oos.max_drawdown_pct is not None else None)
            or (backtest.max_drawdown_pct if backtest else None)
        )
        return ScorecardSnapshotSummary(
            snapshot_id=record.snapshot_id,
            symbol=card.symbol,
            venue=card.venue,
            quote_currency=card.quote_currency,
            branch=card.branch,
            commit_hash=card.commit_hash,
            trigger=record.trigger,
            current_stage=card.lifecycle.current_stage,
            live_return_pct=live.return_pct if live else None,
            oos_return_pct=oos.return_pct if oos else None,
            backtest_return_pct=backtest.return_pct if backtest else None,
            max_drawdown_pct=max_dd,
            drifted=card.latest_drift.drifted if card.latest_drift else None,
            created_at=record.created_at,
        )

    def _discover_symbols(self) -> list[str]:
        discovered: list[str] = []
        if self._configuration_service is not None:
            try:
                config = self._configuration_service.load_config()
                for asset in config.get("assets", []) if isinstance(config, dict) else []:
                    ticker = asset.get("ticker") or asset.get("symbol")
                    if ticker and ticker not in discovered:
                        discovered.append(ticker)
            except Exception:  # pylint: disable=broad-except
                pass

        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresBacktestRepository)
                for session in repo.list_sessions(limit=MAX_LIST_SCAN):
                    if session.ticker_symbol and session.ticker_symbol not in discovered:
                        discovered.append(session.ticker_symbol)
        except Exception:  # pylint: disable=broad-except
            pass

        return discovered

    def _resolve_commit(
            self,
            commit_hash: Optional[str],
            branch: str,
    ) -> tuple[Optional[str], Optional[str]]:
        resolved = commit_hash
        if not resolved:
            ref = f"refs/heads/{branch}" if not branch.startswith("refs/") else branch
            try:
                resolved = self._vcs.resolve_ref(ref)
            except Exception:  # pylint: disable=broad-except
                try:
                    resolved = self._vcs.resolve_ref("HEAD")
                except Exception:  # pylint: disable=broad-except
                    resolved = None

        message: Optional[str] = None
        if resolved:
            try:
                commit = self._vcs.get_commit(resolved)
                message = getattr(commit, "message", None)
            except Exception:  # pylint: disable=broad-except
                message = None
        return resolved, message

    def _load_backtest_stage(
            self,
            symbol: str,
            commit_hash: Optional[str] = None,
    ) -> StageMetrics:
        base = StageMetrics(stage="backtest", label="In-Sample Backtest", status="missing")
        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresBacktestRepository)
                sessions = repo.list_sessions(limit=MAX_LIST_SCAN)
                match = next(
                    (
                        s
                        for s in sessions
                        if s.ticker_symbol == symbol
                        and _commit_matches(
                            getattr(getattr(s.request, "configuration", None), "vcs_commit_hash", None)
                            or getattr(s, "commit_hash", None),
                            commit_hash,
                        )
                    ),
                    None,
                )
                if match is None and commit_hash:
                    match = self._find_backtest_session_via_experiments(
                        uow=uow,
                        backtest_repo=repo,
                        symbol=symbol,
                        commit_hash=commit_hash,
                    )
                if match is None:
                    return base
                metrics = repo.get_result_metrics(match.id) or {}
                result = repo.get_result(match.id)
        except Exception:  # pylint: disable=broad-except
            return base

        status_val = getattr(match.status, "value", str(match.status)).upper()
        stage_status = (
            "running"
            if status_val in ("RUNNING", "QUEUED", "PENDING")
            else ("available" if status_val == "COMPLETED" else "missing")
        )
        return_pct = _first_not_none(
            _as_float(_nested_get(metrics, "portfolio_risk", "total_return_pct")),
            _as_float(metrics.get("total_return_pct")),
            _as_float(metrics.get("percentage_return")),
        )
        if return_pct is None and result and match.request and match.request.initial_balance:
            init_bal = _as_float(match.request.initial_balance)
            final_eq = _as_float(result.final_equity)
            if init_bal and final_eq is not None:
                return_pct = round((final_eq - init_bal) / init_bal * 100.0, 2)

        return StageMetrics(
            stage="backtest",
            label="In-Sample Backtest",
            status=stage_status,
            return_pct=return_pct,
            annualized_return_pct=_as_float(
                _nested_get(metrics, "portfolio_risk", "annualized_return_pct")
            ),
            max_drawdown_pct=_first_not_none(
                _as_float(_nested_get(metrics, "portfolio_risk", "max_drawdown_pct")),
                _as_float(_nested_get(metrics, "risk_adjusted", "max_drawdown_pct")),
                _as_float(metrics.get("max_drawdown_pct")),
            ),
            sharpe_ratio=_first_not_none(
                _as_float(_nested_get(metrics, "risk_adjusted", "sharpe_ratio")),
                _as_float(metrics.get("sharpe_ratio")),
            ),
            win_rate_pct=_first_not_none(
                _as_float(_nested_get(metrics, "trading_behavior", "win_rate_pct")),
                _as_float(_nested_get(metrics, "behavior", "win_rate_pct")),
                _as_float(metrics.get("win_rate_pct")),
            ),
            profit_factor=_first_not_none(
                _as_float(_nested_get(metrics, "trading_behavior", "profit_factor")),
                _as_float(_nested_get(metrics, "behavior", "profit_factor")),
                _as_float(metrics.get("profit_factor")),
            ),
            trade_count=_first_not_none(
                _as_int(_nested_get(metrics, "trading_behavior", "total_trades")),
                _as_int(metrics.get("total_trades")),
                _as_int(metrics.get("round_trips")),
            ),
            total_fees=_first_not_none(
                _as_float(_nested_get(metrics, "execution_quality", "total_fees")),
                _as_float(metrics.get("total_fees")),
            ),
            period_start=match.started_at.isoformat() if match.started_at else None,
            period_end=match.completed_at.isoformat() if match.completed_at else None,
            source_run_id=match.id,
            deep_link=f"/backtests/{match.id}",
        )

    @staticmethod
    def _find_backtest_session_via_experiments(
            uow,
            backtest_repo: PostgresBacktestRepository,
            symbol: str,
            commit_hash: str,
    ):
        exp_repo = uow.get_repository(PostgresExperimentRepository)
        for exp in exp_repo.list_experiments(limit=MAX_LIST_SCAN):
            if exp.get("ticker_symbol") != symbol:
                continue
            spec = exp.get("spec") or {}
            candidates = spec.get("candidates") or []
            matching_candidate_ids = {
                c.get("candidate_id")
                for c in candidates
                if isinstance(c, dict)
                and _commit_matches(c.get("candidate_commit_hash"), commit_hash)
            }
            if not matching_candidate_ids:
                continue
            for binding in exp.get("run_bindings") or []:
                if (
                    isinstance(binding, dict)
                    and binding.get("candidate_id") in matching_candidate_ids
                    and binding.get("backtest_session_id")
                ):
                    session = backtest_repo.get_session(binding["backtest_session_id"])
                    if session is not None:
                        return session
        return None

    def _load_walk_forward_stages(
            self,
            symbol: str,
            commit_hash: Optional[str] = None,
    ) -> tuple[StageMetrics, StageMetrics, list[RegimePerformanceSlice]]:
        is_missing = StageMetrics(stage="walk_forward_is", label="Walk-Forward (In-Sample)", status="missing")
        oos_missing = StageMetrics(stage="walk_forward_oos", label="Walk-Forward (Out-of-Sample)", status="missing")
        try:
            runs = self._walk_forward_service.list_runs(limit=MAX_LIST_SCAN)
        except Exception:  # pylint: disable=broad-except
            return is_missing, oos_missing, []

        match = next(
            (
                r
                for r in runs
                if r.get("ticker_symbol") == symbol
                and _commit_matches(
                    r.get("commit_hash")
                    or _nested_get(r, "spec", "configuration", "vcs_commit_hash")
                    or _nested_get(r, "configuration", "vcs_commit_hash"),
                    commit_hash,
                )
            ),
            None,
        )
        if not match:
            return is_missing, oos_missing, []

        run_id = match.get("run_id") or match.get("id")
        run_status = str(match.get("status", "")).upper()
        stage_status = (
            "running"
            if run_status in ("RUNNING", "QUEUED", "PENDING")
            else ("available" if run_status == "COMPLETED" else "missing")
        )
        summary = match.get("summary") or {}
        folds = summary.get("folds") or []

        is_trades = sum(_as_int(f.get("in_sample_trades")) or 0 for f in folds) if folds else None
        oos_trades = sum(_as_int(f.get("out_of_sample_trades")) or 0 for f in folds) if folds else None
        oos_win_rates = [
            _as_float(f.get("out_of_sample_win_rate_pct"))
            for f in folds
            if _as_float(f.get("out_of_sample_win_rate_pct")) is not None
        ]
        oos_win_rate = round(sum(oos_win_rates) / len(oos_win_rates), 2) if oos_win_rates else None
        oos_pfs = [
            _as_float(f.get("out_of_sample_profit_factor"))
            for f in folds
            if _as_float(f.get("out_of_sample_profit_factor")) is not None
        ]
        oos_pf = round(sum(oos_pfs) / len(oos_pfs), 2) if oos_pfs else None

        deep_link = f"/walk-forward/{run_id}" if run_id else "/walk-forward"
        wf_is = StageMetrics(
            stage="walk_forward_is",
            label="Walk-Forward (In-Sample)",
            status=stage_status,
            return_pct=_as_float(summary.get("in_sample_return_pct")),
            trade_count=is_trades,
            source_run_id=run_id,
            deep_link=deep_link,
        )
        wf_oos = StageMetrics(
            stage="walk_forward_oos",
            label="Walk-Forward (Out-of-Sample)",
            status=stage_status,
            return_pct=_as_float(summary.get("out_of_sample_return_pct")),
            max_drawdown_pct=_as_float(summary.get("max_out_of_sample_drawdown_pct")),
            sharpe_ratio=_as_float(summary.get("out_of_sample_sharpe_ratio")),
            win_rate_pct=oos_win_rate,
            profit_factor=oos_pf,
            trade_count=oos_trades,
            source_run_id=run_id,
            deep_link=deep_link,
        )
        regimes = self._extract_regimes(summary)
        return wf_is, wf_oos, regimes

    @staticmethod
    def _extract_regimes(summary: dict[str, Any]) -> list[RegimePerformanceSlice]:
        raw_regimes = summary.get("regime_breakdown") or summary.get("regimes") or []
        slices: list[RegimePerformanceSlice] = []
        if isinstance(raw_regimes, dict):
            for name, stats in raw_regimes.items():
                if isinstance(stats, dict):
                    slices.append(
                        RegimePerformanceSlice(
                            regime=str(name),
                            return_pct=_as_float(stats.get("return_pct")),
                            max_drawdown_pct=_as_float(stats.get("max_drawdown_pct")),
                            win_rate_pct=_as_float(stats.get("win_rate_pct")),
                            trade_count=_as_int(stats.get("trade_count")) or 0,
                            net_pnl=_as_float(stats.get("net_pnl")),
                        )
                    )
        elif isinstance(raw_regimes, list):
            for entry in raw_regimes:
                if isinstance(entry, dict) and entry.get("regime"):
                    slices.append(
                        RegimePerformanceSlice(
                            regime=str(entry["regime"]),
                            return_pct=_as_float(entry.get("return_pct")),
                            max_drawdown_pct=_as_float(entry.get("max_drawdown_pct")),
                            win_rate_pct=_as_float(entry.get("win_rate_pct")),
                            trade_count=_as_int(entry.get("trade_count")) or 0,
                            net_pnl=_as_float(entry.get("net_pnl")),
                        )
                    )
        return slices

    def _load_simulation_stage(
            self,
            symbol: str,
            commit_hash: Optional[str] = None,
    ) -> tuple[StageMetrics, Optional[str], Optional[GateSummary]]:
        missing = StageMetrics(stage="paper_simulation", label="Paper Simulation", status="missing")
        try:
            runs = self._simulation_orchestrator.list_simulated_runs(limit=MAX_LIST_SCAN)
        except Exception:  # pylint: disable=broad-except
            return missing, None, None

        match = next(
            (
                r
                for r in runs
                if r.get("ticker_symbol") == symbol
                and _commit_matches(
                    r.get("source_commit_hash") or r.get("commit_hash"),
                    commit_hash,
                )
            ),
            None,
        )
        if not match:
            return missing, None, None

        run_id = match.get("run_id") or match.get("id")
        run_status = str(match.get("status", "")).upper()
        stage_status = (
            "running"
            if run_status in ("RUNNING", "PENDING", "STARTING")
            else ("available" if run_status in ("COMPLETED", "CONCLUDED") else "missing")
        )
        report = self._simulation_report_service.get_report_by_run(run_id) if run_id else None
        metrics = (report or {}).get("metrics") or {}
        gate_b = self._parse_gate_summary((report or {}).get("gate_b_evaluation"), "Gate B: Simulation to Main")

        stage = StageMetrics(
            stage="paper_simulation",
            label="Paper Simulation",
            status=stage_status,
            return_pct=_as_float(metrics.get("total_return_pct") or metrics.get("return_pct")),
            max_drawdown_pct=_as_float(metrics.get("max_drawdown_pct")),
            sharpe_ratio=_as_float(metrics.get("sharpe_ratio")),
            win_rate_pct=_as_float(metrics.get("win_rate_pct")),
            profit_factor=_as_float(metrics.get("profit_factor")),
            trade_count=_as_int(metrics.get("total_trades")),
            total_fees=_as_float(metrics.get("total_fees")),
            realized_pnl=_as_float(metrics.get("realized_pnl")),
            period_start=match.get("started_at"),
            period_end=match.get("completed_at"),
            source_run_id=run_id,
            deep_link=f"/simulations/{run_id}" if run_id else "/simulations",
        )
        return stage, run_id, gate_b

    def _load_live_stage(
            self,
            symbol: str,
    ) -> tuple[StageMetrics, list[StrategyAttributionSlice]]:
        missing = StageMetrics(stage="live", label="Live Trading (30d)", status="missing")
        try:
            now = datetime.now(timezone.utc)
            perf: AssetPerformanceResponse = self._asset_performance_service.calculate_performance(
                ticker_symbol=symbol,
                start=now - timedelta(days=DEFAULT_LIVE_LOOKBACK_DAYS),
                end=now,
            )
        except Exception:  # pylint: disable=broad-except
            return missing, []

        summary = perf.summary
        has_trades = bool(summary and summary.trades > 0)
        attribution: list[StrategyAttributionSlice] = []
        for strategy_name, attr in (perf.strategy_attribution or {}).items():
            attribution.append(
                StrategyAttributionSlice(
                    strategy_name=strategy_name,
                    total_trades=attr.total_trades,
                    win_rate_pct=attr.win_rate_pct,
                    net_pnl=_as_float(attr.net_pnl) or 0.0,
                    total_fees=_as_float(attr.total_fees) or 0.0,
                    total_slippage=_as_float(attr.total_slippage) or 0.0,
                    profit_factor=attr.profit_factor,
                )
            )

        if not has_trades:
            return missing, attribution

        return (
            StageMetrics(
                stage="live",
                label="Live Trading (30d)",
                status="available",
                return_pct=_as_float(getattr(perf.portfolio_risk, "total_return_pct", None))
                if hasattr(perf, "portfolio_risk")
                else None,
                max_drawdown_pct=_as_float(getattr(perf.portfolio_risk, "max_drawdown_pct", None))
                if hasattr(perf, "portfolio_risk")
                else None,
                sharpe_ratio=_as_float(getattr(perf.risk_adjusted, "sharpe_ratio", None))
                if hasattr(perf, "risk_adjusted")
                else None,
                win_rate_pct=summary.win_rate,
                profit_factor=summary.profit_factor,
                trade_count=summary.trades,
                total_fees=_as_float(summary.fees),
                realized_pnl=_as_float(summary.realized_pnl),
                period_start=perf.period.start if perf.period else None,
                period_end=perf.period.end if perf.period else None,
                source_run_id=symbol,
                deep_link=f"/performance/{symbol}",
            ),
            attribution,
        )

    def _load_experiment_gate(
            self,
            symbol: str,
    ) -> tuple[Optional[str], Optional[GateSummary]]:
        try:
            experiments = self._experiment_service.list_experiments(limit=MAX_LIST_SCAN)
        except Exception:  # pylint: disable=broad-except
            return None, None

        match = next(
            (e for e in experiments if e.get("ticker_symbol") == symbol),
            None,
        )
        if not match:
            return None, None
        exp_id = match.get("experiment_id") or match.get("id")
        gate_a = self._parse_gate_summary(match.get("gate_a_evaluation"), "Gate A: Experiment to Simulation")
        return exp_id, gate_a

    @staticmethod
    def _parse_gate_summary(
            raw: Optional[dict[str, Any]],
            default_name: str,
    ) -> Optional[GateSummary]:
        if not isinstance(raw, dict):
            return None
        checks = [
            GateCheckSummary(
                name=str(c.get("name", "")),
                status=c.get("status", "SKIPPED"),
                message=str(c.get("message", "")),
            )
            for c in raw.get("checks", [])
            if isinstance(c, dict)
        ]
        decision = raw.get("decision", "PENDING")
        if decision not in ("PASS", "FAIL", "PENDING"):
            decision = "PENDING"
        return GateSummary(
            gate_name=str(raw.get("gate_name") or default_name),
            decision=decision,
            checks=checks,
        )

    @staticmethod
    def _build_lifecycle_progress(
            stages: list[StageMetrics],
            gate_a: Optional[GateSummary],
            gate_b: Optional[GateSummary],
            active_experiment_id: Optional[str],
            active_simulation_id: Optional[str],
    ) -> LifecycleProgress:
        stage_map = {s.stage: s for s in stages}
        completed: list[LifecycleStage] = [LifecycleStage.DRAFT]

        if stage_map["backtest"].status == "available":
            completed.append(LifecycleStage.BACKTESTED)
        if stage_map["walk_forward_oos"].status == "available":
            completed.append(LifecycleStage.WALK_FORWARD_VERIFIED)
        if stage_map["paper_simulation"].status == "available":
            completed.append(LifecycleStage.PAPER_SIMULATED)
        if stage_map["live"].status == "available":
            completed.append(LifecycleStage.LIVE)

        current = completed[-1]
        can_promote = bool(
            stage_map["paper_simulation"].status == "available"
            and (gate_b is None or gate_b.decision == "PASS")
        )
        return LifecycleProgress(
            current_stage=current,
            completed_stages=completed,
            gate_a=gate_a,
            gate_b=gate_b,
            active_experiment_id=active_experiment_id,
            active_simulation_id=active_simulation_id,
            can_promote_to_main=can_promote,
        )
