from __future__ import annotations

import random
import threading
import time
import uuid
from typing import Any, Optional

from api.interfaces.backtest_run_spec import (
    BacktestConfigurationSourceType,
    BacktestConfigurationSpec,
    BacktestRunSpec,
)
from api.interfaces.experiment import (
    CandidateType,
    CreateExperimentRequest,
    ExperimentCandidate,
    ExperimentSpec,
    ExperimentStatus,
    TestSelection,
)
from api.interfaces.walk_forward import (
    WalkForwardRunSpec,
    WalkForwardWindowSpec,
)
from src.configuration.trading_config import TradingConfig
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
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.server.services.backtest_application_service import BacktestApplicationService
from src.server.services.backtest_service import BacktestService
from src.server.services.walk_forward_application_service import WalkForwardApplicationService
from src.vcs.application.service import VCSService
from src.vcs.domain.exceptions import CommitNotFoundError, InvalidReferenceError


class ExperimentApplicationService(ApplicationLoggingMixin):
    def __init__(
            self,
            db_manager: DatabaseManager,
            vcs_service: VCSService,
            backtest_service: BacktestService,
            backtest_app_service: Optional[BacktestApplicationService] = None,
            walk_forward_app_service: Optional[WalkForwardApplicationService] = None,
    ) -> None:
        self._db_manager = db_manager
        self._vcs_service = vcs_service
        self._backtest_service = backtest_service
        self._backtest_app_service = backtest_app_service
        self._walk_forward_app_service = walk_forward_app_service
        self._cancellation_events: dict[str, threading.Event] = {}

    def create_experiment(self, req: CreateExperimentRequest) -> dict[str, Any]:
        base_commit = req.source_commit_hash
        if not base_commit:
            try:
                base_commit = self._vcs_service.resolve_commit_hash("refs/heads/main")
            except (CommitNotFoundError, InvalidReferenceError):
                base_commit = self._vcs_service.resolve_commit_hash("HEAD")

        branch_info = self._backtest_service.create_branch(
            name=f"exp-{req.name}",
            description=f"Experiment branch for {req.name}",
            source_commit_hash=base_commit,
            author="experiment-service",
        )
        branch_id = branch_info["branch_id"]

        current_weights = self._load_asset_strategy_weights(base_commit, req.ticker_symbol)
        candidates: list[ExperimentCandidate] = [
            ExperimentCandidate(
                candidate_id="cand_current",
                name="Current Configuration",
                candidate_type=CandidateType.CURRENT_CONFIG,
                strategy_weights=dict(current_weights),
                description="Configuration as defined in experiment branch",
            )
        ]
        if req.control_policy.enable_equal_weight_baseline:
            equal_weights = {k: 1.0 for k in current_weights} if current_weights else {}
            candidates.append(
                ExperimentCandidate(
                    candidate_id="cand_equal_weight",
                    name="Equal-Weight Strategies",
                    candidate_type=CandidateType.EQUAL_WEIGHT,
                    strategy_weights=equal_weights,
                    description="Equal weight baseline across all registered strategies",
                )
            )
        if req.control_policy.enable_random_pick_control:
            seeds = req.control_policy.random_seeds or [42]
            for seed in seeds:
                candidates.append(
                    ExperimentCandidate(
                        candidate_id=f"cand_random_control_{seed}",
                        name=f"Random Control (Seed {seed})",
                        candidate_type=CandidateType.RANDOM_CONTROL,
                        random_seed=seed,
                        strategy_weights={},
                        description=f"Fixed-seed ({seed}) random selection policy baseline",
                    )
                )

        spec = ExperimentSpec(
            name=req.name,
            ticker_symbol=req.ticker_symbol,
            base_commit_hash=base_commit,
            branch_id=branch_id,
            test_selection=req.test_selection,
            data_source=req.data_source,
            period=req.period,
            windows=req.windows,
            initial_balance=req.initial_balance,
            execution=req.execution,
            control_policy=req.control_policy,
            candidates=candidates,
            triggered_by=req.triggered_by,
        )

        experiment_id = f"exp_{uuid.uuid4().hex[:12]}"
        spec_dict = spec.model_dump(mode="json")

        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            repo.save_experiment(
                experiment_id=experiment_id,
                name=req.name,
                ticker_symbol=req.ticker_symbol,
                branch_id=branch_id,
                base_commit_hash=base_commit,
                status=ExperimentStatus.DRAFT.value,
                spec=spec_dict,
                run_bindings=[],
                report=None,
            )

        self.app_logger.info(
            "Created experiment %s for %s on branch %s (base %s)",
            experiment_id,
            req.ticker_symbol,
            branch_id,
            base_commit[:8],
        )

        return {
            "experiment_id": experiment_id,
            "id": experiment_id,
            "name": req.name,
            "ticker_symbol": req.ticker_symbol,
            "branch_id": branch_id,
            "base_commit_hash": base_commit,
            "status": ExperimentStatus.DRAFT.value,
            "spec": spec_dict,
            "candidates": spec_dict.get("candidates", []),
            "run_bindings": [],
            "report": None,
        }

    def get_experiment(self, experiment_id: str) -> Optional[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            return repo.get_experiment(experiment_id)

    def list_experiments(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            return repo.list_experiments(limit=limit, offset=offset)

    def update_experiment_spec(self, experiment_id: str, spec: ExperimentSpec) -> dict[str, Any]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            existing = repo.get_experiment(experiment_id)
            if not existing:
                raise ValueError(f"Experiment '{experiment_id}' not found.")
            if existing["status"] != ExperimentStatus.DRAFT.value:
                raise ValueError(f"Cannot update experiment '{experiment_id}' in status '{existing['status']}'.")

            spec_dict = spec.model_dump(mode="json")
            repo.save_experiment(
                experiment_id=experiment_id,
                name=spec.name,
                ticker_symbol=spec.ticker_symbol,
                branch_id=existing["branch_id"],
                base_commit_hash=existing["base_commit_hash"],
                status=existing["status"],
                spec=spec_dict,
                run_bindings=existing.get("run_bindings", []),
                report=existing.get("report"),
            )
            return repo.get_experiment(experiment_id) or {}

    def delete_experiment(self, experiment_id: str) -> bool:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            existing = repo.get_experiment(experiment_id)
            if not existing:
                return False

            branch_id = existing.get("branch_id")
            if branch_id:
                try:
                    self._backtest_service.delete_branch(branch_id)
                except Exception as exc:  # pylint: disable=broad-except
                    self.app_logger.warning(
                        "Could not delete branch %s for experiment %s: %s",
                        branch_id,
                        experiment_id,
                        exc,
                    )

            return repo.delete_experiment(experiment_id)

    def start_experiment(self, experiment_id: str) -> dict[str, Any]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            exp = repo.get_experiment(experiment_id)
            if not exp:
                raise ValueError(f"Experiment '{experiment_id}' not found.")
            if exp["status"] in (
                ExperimentStatus.RUNNING.value,
                ExperimentStatus.PREPARING.value,
                ExperimentStatus.AGGREGATING.value,
            ):
                raise ValueError(
                    f"Experiment '{experiment_id}' is already actively executing (status '{exp['status']}')."
                )

            spec = ExperimentSpec.model_validate(exp["spec"])
            for cand in spec.candidates:
                cand.candidate_commit_hash = None
            bindings = self._dispatch_candidate_runs(spec, spec.candidates)
            spec_dict = spec.model_dump(mode="json")

            repo.save_experiment(
                experiment_id=experiment_id,
                name=spec.name,
                ticker_symbol=spec.ticker_symbol,
                branch_id=spec.branch_id,
                base_commit_hash=spec.base_commit_hash,
                status=ExperimentStatus.RUNNING.value,
                spec=spec_dict,
                run_bindings=bindings,
                report=None,
            )

        cancel_evt = threading.Event()
        self._cancellation_events[experiment_id] = cancel_evt
        watcher = threading.Thread(
            target=self._watch_experiment_runs,
            args=(experiment_id,),
            daemon=True,
        )
        watcher.start()

        return self.get_experiment(experiment_id) or {}

    def cancel_experiment(self, experiment_id: str) -> bool:
        if experiment_id in self._cancellation_events:
            self._cancellation_events[experiment_id].set()

        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            exp = repo.get_experiment(experiment_id)
            if not exp:
                return False
            bindings = exp.get("run_bindings", [])
            for b in bindings:
                if b.get("status") == "RUNNING":
                    b["status"] = "CANCELLED"
            repo.update_bindings(experiment_id, bindings)
            repo.update_status(experiment_id, ExperimentStatus.CANCELLED.value)
            return True

    def retry_candidate(self, experiment_id: str, candidate_id: str) -> dict[str, Any]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            exp = repo.get_experiment(experiment_id)
            if not exp:
                raise ValueError(f"Experiment '{experiment_id}' not found.")

            spec = ExperimentSpec.model_validate(exp["spec"])
            target_cand = next((c for c in spec.candidates if c.candidate_id == candidate_id), None)
            if not target_cand:
                raise ValueError(f"Candidate '{candidate_id}' not found in experiment spec.")

            bindings = exp.get("run_bindings", [])
            target_binding = next((b for b in bindings if b.get("candidate_id") == candidate_id), None)
            if not target_binding or target_binding.get("status") != "FAILED":
                raise ValueError(f"Candidate '{candidate_id}' is not in a FAILED state.")

            new_bindings = self._dispatch_candidate_runs(spec, [target_cand])
            if new_bindings:
                target_binding.update(new_bindings[0])

            repo.update_bindings(experiment_id, bindings)
            repo.update_status(experiment_id, ExperimentStatus.RUNNING.value)

        cancel_evt = threading.Event()
        self._cancellation_events[experiment_id] = cancel_evt
        watcher = threading.Thread(
            target=self._watch_experiment_runs,
            args=(experiment_id,),
            daemon=True,
        )
        watcher.start()

        return self.get_experiment(experiment_id) or {}

    @staticmethod
    def _apply_candidate_weights(
            cand: ExperimentCandidate,
            strategies: list[Any],
    ) -> Optional[tuple[list[Any], str]]:
        if cand.candidate_type == CandidateType.EQUAL_WEIGHT:
            updated = [s.model_copy(update={"weight": 1.0}) for s in strategies]
            msg = f"Experiment candidate variant: Equal-Weight ({cand.candidate_id})"
            return updated, msg

        if cand.candidate_type == CandidateType.PROPOSED_WEIGHTS and cand.strategy_weights:
            updated = [
                s.model_copy(update={"weight": float(cand.strategy_weights[s.name])})
                if s.name and s.name in cand.strategy_weights else s
                for s in strategies
            ]
            msg = f"Experiment candidate variant: {cand.name} ({cand.candidate_id})"
            return updated, msg

        if cand.candidate_type == CandidateType.RANDOM_CONTROL:
            rng = random.Random(cand.random_seed or 42)
            enabled_strats = [s for s in strategies if getattr(s, "enabled", True)]
            raw_weights = [rng.uniform(0.1, 1.0) for _ in enabled_strats]
            total = sum(raw_weights) or 1.0
            norm_weights = [round(w / total, 4) for w in raw_weights]
            cand.strategy_weights = {
                s.name: w for s, w in zip(enabled_strats, norm_weights) if s.name
            }
            updated = [
                s.model_copy(update={"weight": cand.strategy_weights.get(s.name, s.weight)})
                for s in strategies
            ]
            msg = (
                f"Experiment candidate variant: Random Control "
                f"Seed {cand.random_seed} ({cand.candidate_id})"
            )
            return updated, msg

        return None

    def _load_asset_strategy_weights(self, commit_hash: str, ticker: str) -> dict[str, float]:
        try:
            raw_config = self._vcs_service.checkout(commit_hash)
            trading_config = TradingConfig.model_validate(raw_config)
            matched = next((a for a in trading_config.assets if a.ticker_symbol == ticker), None)
            if matched and matched.strategies:
                return {
                    s.name: float(s.weight)
                    for s in matched.strategies
                    if s.name and getattr(s, "enabled", True)
                }
        except Exception:  # pylint: disable=broad-except
            pass
        return {}

    def _resolve_candidate_commit(
            self,
            branch_id: str,
            ticker_symbol: str,
            cand: ExperimentCandidate,
    ) -> str:
        if cand.candidate_commit_hash:
            return cand.candidate_commit_hash

        branch_ref = f"refs/heads/backtest/{branch_id}"
        head_commit = self._vcs_service.resolve_commit_hash(branch_ref)

        if cand.candidate_type == CandidateType.CURRENT_CONFIG:
            cand.strategy_weights = self._load_asset_strategy_weights(head_commit, ticker_symbol)
            cand.candidate_commit_hash = head_commit
            return head_commit

        if cand.candidate_type == CandidateType.EQUAL_WEIGHT:
            weights = self._load_asset_strategy_weights(head_commit, ticker_symbol)
            cand.strategy_weights = {k: 1.0 for k in weights}

        try:
            raw_config = self._vcs_service.checkout(head_commit)
            trading_config = TradingConfig.model_validate(raw_config)
            matched_asset = next((a for a in trading_config.assets if a.ticker_symbol == ticker_symbol), None)

            if matched_asset and matched_asset.strategies:
                variant_update = self._apply_candidate_weights(cand, matched_asset.strategies)
                if variant_update:
                    updated_strats, commit_msg = variant_update
                    matched_asset.strategies = updated_strats
                    commit = self._vcs_service.commit(
                        content=trading_config,
                        author="experiment-service",
                        message=commit_msg,
                        ref=branch_ref,
                    )
                    cand.candidate_commit_hash = commit.hash
                    return commit.hash
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.warning(
                "Could not synthesize committed variant for candidate %s: %s",
                cand.candidate_id,
                exc,
            )

        cand.candidate_commit_hash = head_commit
        return head_commit

    def _dispatch_candidate_runs(
            self,
            spec: ExperimentSpec,
            candidates: list[ExperimentCandidate],
    ) -> list[dict[str, Any]]:
        bindings: list[dict[str, Any]] = []

        for cand in candidates:
            commit_hash = self._resolve_candidate_commit(spec.branch_id, spec.ticker_symbol, cand)
            bt_session_id = None
            wf_run_id = None

            if spec.test_selection in (TestSelection.BACKTEST_ONLY, TestSelection.BOTH):
                if self._backtest_app_service:
                    bt_spec = BacktestRunSpec(
                        ticker_symbol=spec.ticker_symbol,
                        configuration=BacktestConfigurationSpec(
                            source_type=BacktestConfigurationSourceType.VCS,
                            vcs_commit_hash=commit_hash,
                        ),
                        data_source=spec.data_source,
                        period=spec.period,
                        initial_balance=spec.initial_balance,
                        execution=spec.execution,
                    )
                    bt_session = self._backtest_app_service.start_backtest_run(bt_spec)
                    bt_session_id = bt_session.id

            if spec.test_selection in (TestSelection.WALK_FORWARD_ONLY, TestSelection.BOTH):
                if self._walk_forward_app_service:
                    wf_spec = WalkForwardRunSpec(
                        ticker_symbol=spec.ticker_symbol,
                        configuration=BacktestConfigurationSpec(
                            source_type=BacktestConfigurationSourceType.VCS,
                            vcs_commit_hash=commit_hash,
                        ),
                        data_source=spec.data_source,
                        period=spec.period,
                        windows=spec.windows or WalkForwardWindowSpec(),
                        initial_balance=spec.initial_balance,
                        execution=spec.execution,
                        candidate_weights=cand.strategy_weights if cand.strategy_weights else None,
                    )
                    wf_run = self._walk_forward_app_service.start_run(wf_spec)
                    wf_run_id = wf_run["run_id"]

            bindings.append({
                "candidate_id": cand.candidate_id,
                "backtest_session_id": bt_session_id,
                "walk_forward_run_id": wf_run_id,
                "status": "RUNNING",
                "error": None,
            })

        return bindings

    def _watch_experiment_runs(self, experiment_id: str) -> None:  # pylint: disable=too-many-locals
        cancel_evt = self._cancellation_events.get(experiment_id)
        while True:
            if cancel_evt and cancel_evt.is_set():
                self.app_logger.info("Experiment %s cancelled during monitoring", experiment_id)
                with self._db_manager.get_unit_of_work() as uow:
                    repo = uow.get_repository(PostgresExperimentRepository)
                    repo.update_status(experiment_id, ExperimentStatus.CANCELLED.value)
                return

            time.sleep(0.5)

            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresExperimentRepository)
                exp = repo.get_experiment(experiment_id)
                if not exp or exp["status"] in (
                    ExperimentStatus.COMPLETED.value,
                    ExperimentStatus.FAILED.value,
                    ExperimentStatus.CANCELLED.value,
                ):
                    return

                bindings = exp.get("run_bindings", [])
                all_done = True
                any_failed = False
                updated = False

                for b in bindings:
                    if b.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
                        continue

                    bt_done, wf_done, b_failed, error_msg = self._poll_binding_status(uow, b)
                    if b_failed:
                        b["status"] = "FAILED"
                        b["error"] = error_msg
                        updated = True
                        any_failed = True
                    elif bt_done and wf_done:
                        b["status"] = "COMPLETED"
                        updated = True
                    else:
                        all_done = False

                if updated:
                    repo.update_bindings(experiment_id, bindings)

                if all_done:
                    spec_dict = exp.get("spec", {})
                    spec = ExperimentSpec.model_validate(spec_dict)
                    repo.update_status(experiment_id, ExperimentStatus.AGGREGATING.value)
                    report = self._compute_experiment_report(uow, spec, bindings, self._vcs_service)
                    final_status = (
                        ExperimentStatus.FAILED.value
                        if (any_failed and all(b.get("status") == "FAILED" for b in bindings))
                        else ExperimentStatus.COMPLETED.value
                    )
                    repo.update_report(experiment_id, final_status, report)
                    self.app_logger.info("Experiment %s finished with status %s", experiment_id, final_status)
                    return

    @staticmethod
    def _poll_binding_status(uow: Any, b: dict[str, Any]) -> tuple[bool, bool, bool, Optional[str]]:
        bt_done = True
        wf_done = True
        b_failed = False
        error_msg = None

        if b.get("backtest_session_id"):
            bt_repo = uow.get_repository(PostgresBacktestRepository)
            bt_session = bt_repo.get_session(b["backtest_session_id"])
            if bt_session:
                status_str = (
                    bt_session.status.value
                    if hasattr(bt_session.status, "value")
                    else str(bt_session.status)
                )
                if status_str == "RUNNING":
                    bt_done = False
                elif status_str == "FAILED":
                    b_failed = True
                    error_msg = bt_session.error_message or "Backtest run failed"
            else:
                bt_done = False

        if b.get("walk_forward_run_id"):
            wf_repo = uow.get_repository(PostgresWalkForwardRepository)
            wf_run = wf_repo.get_run(b["walk_forward_run_id"])
            if wf_run:
                wf_status = wf_run.get("status")
                if wf_status == "RUNNING":
                    wf_done = False
                elif wf_status == "FAILED":
                    b_failed = True
                    error_msg = wf_run.get("error_message") or "Walk-forward run failed"
            else:
                wf_done = False

        return bt_done, wf_done, b_failed, error_msg

    @classmethod
    def _compute_experiment_report(  # pylint: disable=too-many-locals
            cls,
            uow: Any,
            spec: ExperimentSpec,
            bindings: list[dict[str, Any]],
            vcs_service: Optional[VCSService] = None,
    ) -> dict[str, Any]:
        bt_repo = uow.get_repository(PostgresBacktestRepository)
        wf_repo = uow.get_repository(PostgresWalkForwardRepository)

        candidate_reports: dict[str, Any] = {}
        baseline_bt_ret: Optional[float] = None
        baseline_wf_ret: Optional[float] = None

        cand_map = {c.candidate_id: c for c in spec.candidates}

        for b in bindings:
            cid = b["candidate_id"]
            cand_obj = cand_map.get(cid)
            cand_entry: dict[str, Any] = {
                "candidate_id": cid,
                "name": cand_obj.name if cand_obj else cid,
                "candidate_type": cand_obj.candidate_type.value if cand_obj else "CUSTOM",
                "status": b.get("status"),
                "error": b.get("error"),
                "backtest": None,
                "walk_forward": None,
            }

            if b.get("backtest_session_id"):
                metrics = bt_repo.get_result_metrics(b["backtest_session_id"])
                cand_entry["backtest"] = metrics
                if cid == "cand_current" and metrics:
                    baseline_bt_ret = float(metrics.get("percentage_return", 0.0))

            if b.get("walk_forward_run_id"):
                wf_run = wf_repo.get_run(b["walk_forward_run_id"])
                if wf_run and wf_run.get("summary"):
                    cand_entry["walk_forward"] = wf_run["summary"]
                    if cid == "cand_current":
                        baseline_wf_ret = float(wf_run["summary"].get("aggregate_oos_return_pct", 0.0))

            candidate_reports[cid] = cand_entry

        # Compute deltas vs current configuration baseline
        for cid, entry in candidate_reports.items():
            deltas: dict[str, Any] = {}
            if entry.get("backtest") and baseline_bt_ret is not None:
                bt_ret = float(entry["backtest"].get("percentage_return", 0.0))
                deltas["backtest_return_diff"] = round(bt_ret - baseline_bt_ret, 4)
            if entry.get("walk_forward") and baseline_wf_ret is not None:
                wf_ret = float(entry["walk_forward"].get("aggregate_oos_return_pct", 0.0))
                deltas["walk_forward_oos_return_diff"] = round(wf_ret - baseline_wf_ret, 4)
            entry["deltas"] = deltas

        total_cands = len(bindings)
        completed_cands = sum(1 for b in bindings if b.get("status") == "COMPLETED")
        strat_attr, combo_matrix, strat_actions, strat_weights, strat_regime, regime_attr = (
            cls._extract_strategy_matrices(
                candidate_reports, spec=spec, vcs_service=vcs_service
            )
        )

        return {
            "summary": {
                "total_candidates": total_cands,
                "completed_candidates": completed_cands,
                "failed_candidates": total_cands - completed_cands,
                "test_selection": spec.test_selection.value,
            },
            "candidates": candidate_reports,
            "strategy_attribution": strat_attr,
            "strategy_combination_matrix": combo_matrix,
            "strategy_actions": strat_actions,
            "strategy_weights": strat_weights,
            "strategy_regime_matrix": strat_regime,
            "regime_attribution": regime_attr,
        }

    @classmethod
    def _extract_strategy_matrices(  # pylint: disable=too-many-locals
            cls,
            candidate_reports: dict[str, Any],
            spec: Optional[ExperimentSpec] = None,
            vcs_service: Optional[VCSService] = None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, str], dict[str, float], dict[str, Any], dict[str, Any]]:
        strat_attr: dict[str, Any] = {}
        co_matrix: dict[str, Any] = {}
        co_counts: dict[str, Any] = {}
        co_by_regime: dict[str, Any] = {}
        strat_regime_matrix: dict[str, Any] = {}
        regime_attr: dict[str, Any] = {}

        candidate_keys = ["cand_current", *candidate_reports.keys()]
        for cid in candidate_keys:
            rep = candidate_reports.get(cid)
            if not rep or not rep.get("backtest"):
                continue
            bt = rep["backtest"]
            if not strat_attr and bt.get("strategy_attribution"):
                strat_attr = dict(bt["strategy_attribution"])
            if not co_matrix and bt.get("co_voting_matrix"):
                co_matrix = dict(bt["co_voting_matrix"])
                co_counts = dict(bt.get("co_voting_counts", {}))
            if not co_by_regime and bt.get("co_voting_by_regime"):
                co_by_regime = dict(bt["co_voting_by_regime"])
            if not strat_regime_matrix and bt.get("strategy_regime_matrix"):
                strat_regime_matrix = dict(bt["strategy_regime_matrix"])
            if not regime_attr and bt.get("regime_attribution"):
                regime_attr = dict(bt["regime_attribution"])
            if strat_attr and co_matrix and co_by_regime and strat_regime_matrix:
                break

        strat_actions, strat_weights = cls._resolve_strategy_metadata(spec, vcs_service)
        cls._harmonize_strategy_matrices(
            strat_attr, co_matrix, co_counts, co_by_regime, strat_regime_matrix,
            strat_actions, strat_weights, spec, regime_attr
        )

        combination_spec = {
            "matrix": co_matrix,
            "counts": co_counts,
            "by_regime": co_by_regime,
        }
        return strat_attr, combination_spec, strat_actions, strat_weights, strat_regime_matrix, regime_attr

    @staticmethod
    def _resolve_target_commit(
            spec: Optional[ExperimentSpec],
            vcs_service: Optional[VCSService],
    ) -> Optional[str]:
        if not spec or not vcs_service:
            return None
        if spec.branch_id:
            try:
                branch_ref = f"refs/heads/backtest/{spec.branch_id}"
                return vcs_service.resolve_commit_hash(branch_ref)
            except Exception:  # pylint: disable=broad-except
                pass
        return spec.base_commit_hash

    @classmethod
    def _resolve_strategy_metadata(
            cls,
            spec: Optional[ExperimentSpec],
            vcs_service: Optional[VCSService],
    ) -> tuple[dict[str, str], dict[str, float]]:
        strat_actions: dict[str, str] = {}
        strat_weights: dict[str, float] = {}
        commit_hash = cls._resolve_target_commit(spec, vcs_service)
        if commit_hash and vcs_service and spec:
            try:
                raw_config = vcs_service.checkout(commit_hash)
                trading_config = TradingConfig.model_validate(raw_config)
                matched = next(
                    (a for a in trading_config.assets if a.ticker_symbol == spec.ticker_symbol),
                    None,
                )
                if matched and matched.strategies:
                    for s in matched.strategies:
                        if s.name and getattr(s, "enabled", True):
                            action_val = s.action.value if hasattr(s.action, "value") else str(s.action or "BUY")
                            strat_actions[s.name] = action_val
                            strat_weights[s.name] = float(s.weight)
            except Exception:  # pylint: disable=broad-except
                pass

        if spec and not strat_weights:
            for cand in spec.candidates:
                if cand.candidate_type == CandidateType.CURRENT_CONFIG and cand.strategy_weights:
                    strat_weights.update(cand.strategy_weights)
                    break
        return strat_actions, strat_weights

    @staticmethod
    def _resolve_strategy_action(name: str, strat_actions: dict[str, str]) -> str:
        if name in strat_actions:
            return strat_actions[name]
        lower = name.lower()
        if "buy" in lower or "long" in lower:
            return "BUY"
        if "sell" in lower or "short" in lower:
            return "SELL"
        return "ALL"

    @classmethod
    def _harmonize_strategy_attribution(
            cls,
            strat_attr: dict[str, Any],
            all_names: set[str],
            strat_actions: dict[str, str],
            strat_weights: dict[str, float],
    ) -> None:
        for name in all_names:
            action_val = cls._resolve_strategy_action(name, strat_actions)
            weight_val = strat_weights.get(name, 1.0)
            if name not in strat_attr:
                strat_attr[name] = {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "win_rate_pct": 0.0,
                    "net_pnl": 0.0,
                    "profit_factor": 0.0,
                    "avg_return_pct": 0.0,
                    "max_win": 0.0,
                    "max_loss": 0.0,
                    "action": action_val,
                    "weight": weight_val,
                }
            else:
                if "action" not in strat_attr[name]:
                    strat_attr[name]["action"] = action_val
                strat_attr[name]["weight"] = weight_val

    @staticmethod
    def _harmonize_co_voting_matrix(
            co_matrix: dict[str, Any],
            co_counts: dict[str, Any],
            strat_attr: dict[str, Any],
            all_names: set[str],
    ) -> None:
        for r in all_names:
            if r not in co_matrix:
                co_matrix[r] = {}
                co_counts[r] = {}
            for c in all_names:
                if c not in co_matrix[r]:
                    if r == c:
                        co_matrix[r][c] = 1.0
                        co_counts[r][c] = strat_attr.get(r, {}).get("total_trades", 0)
                    else:
                        co_matrix[r][c] = 0.0
                        co_counts[r][c] = 0

    @classmethod
    def _harmonize_co_by_regime(
            cls,
            co_by_regime: dict[str, Any],
            standard_regimes: tuple[str, ...],
            strat_attr: dict[str, Any],
            all_names: set[str],
    ) -> None:
        for reg in standard_regimes:
            if reg not in co_by_regime:
                co_by_regime[reg] = {"matrix": {}, "counts": {}}

        for r_data in co_by_regime.values():
            if isinstance(r_data, dict) and "matrix" in r_data and "counts" in r_data:
                cls._harmonize_co_voting_matrix(r_data["matrix"], r_data["counts"], strat_attr, all_names)

    @classmethod
    def _harmonize_regime_matrices(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            cls,
            co_by_regime: dict[str, Any],
            strat_regime_matrix: dict[str, Any],
            strat_attr: dict[str, Any],
            all_names: set[str],
            regime_attr: Optional[dict[str, Any]] = None,
    ) -> None:
        standard_regimes = (
            "TRENDING_UP",
            "TRENDING_DOWN",
            "HIGH_VOLATILITY",
            "LOW_VOLATILITY",
            "RANGING",
        )
        cls._harmonize_co_by_regime(co_by_regime, standard_regimes, strat_attr, all_names)

        known_regimes: set[str] = set(standard_regimes)
        for r_map in strat_regime_matrix.values():
            if isinstance(r_map, dict):
                known_regimes.update(r_map.keys())

        empty_metrics = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate_pct": 0.0,
            "net_pnl": 0.0,
            "profit_factor": 0.0,
            "avg_return_pct": 0.0,
            "max_win": 0.0,
            "max_loss": 0.0,
        }

        for name in all_names:
            if name not in strat_regime_matrix:
                strat_regime_matrix[name] = {}
            for regime in known_regimes:
                if regime not in strat_regime_matrix[name]:
                    strat_regime_matrix[name][regime] = dict(empty_metrics)

        if regime_attr is not None:
            for reg in standard_regimes:
                if reg not in regime_attr:
                    regime_attr[reg] = dict(empty_metrics)

    @classmethod
    def _harmonize_strategy_matrices(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            cls,
            strat_attr: dict[str, Any],
            co_matrix: dict[str, Any],
            co_counts: dict[str, Any],
            co_by_regime: dict[str, Any],
            strat_regime_matrix: dict[str, Any],
            strat_actions: dict[str, str],
            strat_weights: dict[str, float],
            spec: Optional[ExperimentSpec],
            regime_attr: Optional[dict[str, Any]] = None,
    ) -> None:
        all_names = set(strat_attr.keys()) | set(strat_actions.keys()) | set(strat_weights.keys())
        if spec:
            for cand in spec.candidates:
                if cand.strategy_weights:
                    all_names.update(cand.strategy_weights.keys())

        cls._harmonize_strategy_attribution(strat_attr, all_names, strat_actions, strat_weights)
        cls._harmonize_co_voting_matrix(co_matrix, co_counts, strat_attr, all_names)
        cls._harmonize_regime_matrices(co_by_regime, strat_regime_matrix, strat_attr, all_names, regime_attr)
