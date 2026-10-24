from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from api.interfaces.backtest_run_spec import BacktestPeriodSpec
from api.interfaces.evidence_proposal import GenerateCommitProposalRequest
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_backtest_repository import (
    PostgresBacktestRepository,
)
from src.database.repositories.providers.postgres_experiment_repository import (
    PostgresExperimentRepository,
)
from src.database.repositories.providers.postgres_walk_forward_repository import (
    PostgresWalkForwardRepository,
)
from src.proposals.models import CollectedEvidence
from src.vcs.application.service import VCSService
from src.vcs.domain.diff import ConfigChange

BASELINE_CANDIDATE_ID = "cand_current"


class EvidenceCollector:
    def __init__(
            self,
            db_manager: DatabaseManager,
            vcs_service: Optional[VCSService] = None,
    ):
        self._db_manager = db_manager
        self._vcs_service = vcs_service

    def collect_from_experiment(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            experiment_id: str,
            candidate_id: str,
            hypothesis: Optional[str] = None,
            title: Optional[str] = None,
            triggered_by: Optional[dict[str, Any]] = None,
    ) -> CollectedEvidence:
        exp_dict = self._fetch_experiment_dict(experiment_id)
        spec = exp_dict.get("spec") or {}
        base_bind = self._find_binding(exp_dict.get("run_bindings") or [], BASELINE_CANDIDATE_ID) or {}
        cand_bind = self._find_binding(exp_dict.get("run_bindings") or [], candidate_id) or {}
        cand_spec = self._find_candidate_spec(spec.get("candidates") or [], candidate_id) or {}

        run_records = self._load_run_records(
            base_bt_id=base_bind.get("backtest_session_id"),
            cand_bt_id=cand_bind.get("backtest_session_id"),
            base_wf_id=base_bind.get("walk_forward_run_id"),
            cand_wf_id=cand_bind.get("walk_forward_run_id"),
        )
        base_cfg, cand_cfg, changes = self._resolve_vcs_configs(
            exp_dict.get("base_commit_hash") or spec.get("base_commit_hash") or "HEAD",
            cand_spec.get("candidate_commit_hash"),
            cand_spec,
        )

        return CollectedEvidence(
            ticker_symbol=exp_dict.get("ticker_symbol", "UNKNOWN"),
            baseline_commit=exp_dict.get("base_commit_hash") or spec.get("base_commit_hash") or "HEAD",
            candidate_commit=cand_spec.get("candidate_commit_hash"),
            candidate_id=candidate_id,
            candidate_name=cand_spec.get("name") or candidate_id,
            experiment_id=experiment_id,
            experiment_name=exp_dict.get("name"),
            total_candidates_tested=max(
                len(spec.get("candidates") or []),
                len(exp_dict.get("run_bindings") or []),
                1,
            ),
            baseline_backtest_id=base_bind.get("backtest_session_id"),
            candidate_backtest_id=cand_bind.get("backtest_session_id"),
            baseline_walk_forward_id=base_bind.get("walk_forward_run_id"),
            candidate_walk_forward_id=cand_bind.get("walk_forward_run_id"),
            dataset_id=self._extract_dataset_id(spec),
            baseline_session=run_records["base_session"],
            candidate_session=run_records["cand_session"],
            baseline_bt_metrics=run_records["base_bt_metrics"],
            candidate_bt_metrics=run_records["cand_bt_metrics"],
            baseline_wf_run=run_records["base_wf_run"],
            candidate_wf_run=run_records["cand_wf_run"],
            config_changes=changes,
            baseline_config=base_cfg,
            candidate_config=cand_cfg,
            evaluation_period=self._parse_period(spec.get("period")),
            market_data_provenance=self._extract_provenance(spec),
            execution_assumptions=dict(spec.get("execution") or {}),
            hypothesis=hypothesis or cand_spec.get("description"),
            title=title,
            triggered_by=triggered_by or spec.get("triggered_by"),
        )

    def collect_from_commits(
            self,
            req: GenerateCommitProposalRequest,
    ) -> CollectedEvidence:
        run_records = self._load_run_records(
            base_bt_id=req.baseline_backtest_id,
            cand_bt_id=req.candidate_backtest_id,
            base_wf_id=req.baseline_walk_forward_id,
            cand_wf_id=req.candidate_walk_forward_id,
        )
        base_cfg, cand_cfg, changes = self._resolve_vcs_configs(
            req.baseline_commit, req.candidate_commit, None
        )
        base_session = run_records["base_session"]
        period, exec_assumptions, provenance = self._extract_session_metadata(base_session)

        return CollectedEvidence(
            ticker_symbol=req.ticker_symbol,
            baseline_commit=req.baseline_commit,
            candidate_commit=req.candidate_commit,
            baseline_backtest_id=req.baseline_backtest_id,
            candidate_backtest_id=req.candidate_backtest_id,
            baseline_walk_forward_id=req.baseline_walk_forward_id,
            candidate_walk_forward_id=req.candidate_walk_forward_id,
            baseline_session=base_session,
            candidate_session=run_records["cand_session"],
            baseline_bt_metrics=run_records["base_bt_metrics"],
            candidate_bt_metrics=run_records["cand_bt_metrics"],
            baseline_wf_run=run_records["base_wf_run"],
            candidate_wf_run=run_records["cand_wf_run"],
            config_changes=changes,
            baseline_config=base_cfg,
            candidate_config=cand_cfg,
            evaluation_period=period,
            market_data_provenance=provenance,
            execution_assumptions=exec_assumptions,
            hypothesis=req.hypothesis,
            title=req.title,
            triggered_by=req.triggered_by,
        )

    def _fetch_experiment_dict(self, experiment_id: str) -> dict[str, Any]:
        with self._db_manager.get_unit_of_work() as uow:
            exp_repo = uow.get_repository(PostgresExperimentRepository)
            exp_dict = exp_repo.get_experiment(experiment_id)
            if not exp_dict:
                raise ValueError(f"Experiment '{experiment_id}' not found.")
            return exp_dict

    def _load_run_records(
            self,
            base_bt_id: Optional[str],
            cand_bt_id: Optional[str],
            base_wf_id: Optional[str],
            cand_wf_id: Optional[str],
    ) -> dict[str, Any]:
        with self._db_manager.get_unit_of_work() as uow:
            bt_repo = uow.get_repository(PostgresBacktestRepository)
            wf_repo = uow.get_repository(PostgresWalkForwardRepository)
            return {
                "base_session": bt_repo.get_session(base_bt_id) if base_bt_id else None,
                "cand_session": bt_repo.get_session(cand_bt_id) if cand_bt_id else None,
                "base_bt_metrics": bt_repo.get_result_metrics(base_bt_id) if base_bt_id else None,
                "cand_bt_metrics": bt_repo.get_result_metrics(cand_bt_id) if cand_bt_id else None,
                "base_wf_run": wf_repo.get_run(base_wf_id) if base_wf_id else None,
                "cand_wf_run": wf_repo.get_run(cand_wf_id) if cand_wf_id else None,
            }

    @staticmethod
    def _extract_session_metadata(
            base_session: Any,
    ) -> tuple[Optional[BacktestPeriodSpec], dict[str, Any], Optional[str]]:
        if not base_session:
            return None, {}, None
        period = BacktestPeriodSpec(
            start_time=base_session.request.start_time,
            end_time=base_session.request.end_time,
        )
        exec_assumptions = {
            "latency_ms": base_session.request.execution.latency_ms,
            "slippage_ticks": base_session.request.execution.slippage_ticks,
            "fee_rate": str(base_session.request.execution.fee_rate),
        }
        provenance = (
            base_session.request.data_source.path
            or base_session.request.data_source.source_type.value
        )
        return period, exec_assumptions, provenance

    @staticmethod
    def _find_binding(
            bindings: list[dict[str, Any]],
            candidate_id: str,
    ) -> Optional[dict[str, Any]]:
        for binding in bindings:
            if binding.get("candidate_id") == candidate_id:
                return binding
        return None

    @staticmethod
    def _find_candidate_spec(
            candidates: list[dict[str, Any]],
            candidate_id: str,
    ) -> Optional[dict[str, Any]]:
        for cand in candidates:
            if cand.get("candidate_id") == candidate_id:
                return cand
        return None

    @staticmethod
    def _extract_dataset_id(spec: dict[str, Any]) -> Optional[str]:
        ds = spec.get("data_source") or {}
        return ds.get("dataset_id") or ds.get("path")

    @classmethod
    def _extract_provenance(cls, spec: dict[str, Any]) -> Optional[str]:
        ds = spec.get("data_source") or {}
        val = cls._extract_dataset_id(spec) or ds.get("source_type")
        return str(val) if val else None

    @staticmethod
    def _parse_period(raw_period: Optional[dict[str, Any]]) -> Optional[BacktestPeriodSpec]:
        if not raw_period:
            return None
        start = raw_period.get("start_time")
        end = raw_period.get("end_time")
        start_dt = datetime.fromisoformat(start) if isinstance(start, str) else start
        end_dt = datetime.fromisoformat(end) if isinstance(end, str) else end
        return BacktestPeriodSpec(start_time=start_dt, end_time=end_dt)

    def _resolve_vcs_configs(
            self,
            baseline_commit: str,
            candidate_commit: Optional[str],
            candidate_spec: Optional[dict[str, Any]],
    ) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], list[ConfigChange]]:
        baseline_cfg: Optional[dict[str, Any]] = None
        candidate_cfg: Optional[dict[str, Any]] = None
        changes: list[ConfigChange] = []

        if self._vcs_service:
            try:
                baseline_cfg = self._vcs_service.checkout(baseline_commit)
            except Exception:  # pylint: disable=broad-except
                baseline_cfg = None

            if candidate_commit:
                try:
                    candidate_cfg = self._vcs_service.checkout(candidate_commit)
                except Exception:  # pylint: disable=broad-except
                    candidate_cfg = None

            if baseline_commit and candidate_commit and baseline_commit != candidate_commit:
                try:
                    changes = self._vcs_service.diff(baseline_commit, candidate_commit)
                except Exception:  # pylint: disable=broad-except
                    changes = []

        if not changes and candidate_spec and candidate_spec.get("strategy_weights"):
            for strat_name, weight in candidate_spec["strategy_weights"].items():
                changes.append(
                    ConfigChange(
                        path=f"strategies.{strat_name}.weight",
                        old_value=None,
                        new_value=weight,
                        reason=f"Candidate weight adjustment for {strat_name}",
                    )
                )

        return baseline_cfg, candidate_cfg, changes
