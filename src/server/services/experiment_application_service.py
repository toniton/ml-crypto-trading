from __future__ import annotations

import random
import threading
import time
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from api.interfaces.backtest_run_spec import (
    BacktestConfigurationSourceType,
    BacktestConfigurationSpec,
    BacktestMarketDataSpec,
    BacktestPeriodSpec,
    BacktestRunSpec,
)
from api.interfaces.experiment import (
    CandidateType,
    CreateExperimentRequest,
    ExperimentCandidate,
    ExperimentRunConfigSnapshot,
    ExperimentRunHistoryEntry,
    ExperimentSpec,
    ExperimentStatus,
    StartExperimentRequest,
    TestSelection,
)
from api.interfaces.walk_forward import (
    WalkForwardRunSpec,
    WalkForwardWindowSpec,
)
from src.configuration.strategy_config import StrategyConfig
from src.configuration.trading_config import TradingConfig
from src.core.hooks import (
    HookCatalog,
    HookContext,
    HookExecutionMode,
    HookManager,
    HookStage,
)
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
            hook_manager: Optional[HookManager] = None,
    ) -> None:
        self._db_manager = db_manager
        self._vcs_service = vcs_service
        self._backtest_service = backtest_service
        self._backtest_app_service = backtest_app_service
        self._walk_forward_app_service = walk_forward_app_service
        self._hook_manager = hook_manager
        self._cancellation_events: dict[str, threading.Event] = {}
        self._active_run_meta: dict[str, dict[str, Any]] = {}
        self._on_experiment_completed: Optional[Any] = None

    def set_completion_hook(self, callback: Any) -> None:
        if self._hook_manager is not None:
            def _legacy_adapter(ctx: HookContext) -> None:
                symbol = ctx.payload.get("ticker_symbol")
                commit_hash = ctx.payload.get("base_commit_hash")
                if symbol:
                    callback(symbol, commit_hash)

            self._hook_manager.register(
                HookCatalog.EXPERIMENT_RUN,
                _legacy_adapter,
                stages=(HookStage.COMPLETED,),
                mode=HookExecutionMode.ASYNC,
                priority=50,
                name="legacy_experiment_completion_hook",
            )
            return
        self._on_experiment_completed = callback

    def _emit_experiment_hook(  # pylint: disable=too-many-arguments
            self,
            stage: HookStage,
            experiment_id: str,
            spec: ExperimentSpec,
            status: str,
            previous_state: Optional[str] = None,
            report: Optional[dict[str, Any]] = None,
            error: Optional[str] = None,
    ) -> None:
        if self._hook_manager is None:
            return
        payload: dict[str, Any] = {
            "experiment_id": experiment_id,
            "name": spec.name,
            "ticker_symbol": spec.ticker_symbol,
            "branch_id": spec.branch_id,
            "base_commit_hash": spec.base_commit_hash,
            "status": status,
            "report": report,
            "triggered_by": spec.triggered_by,
            "candidates": [c.model_dump(mode="json") for c in spec.candidates],
        }
        self._hook_manager.emit(
            HookContext(
                hook_name=HookCatalog.EXPERIMENT_RUN,
                stage=stage,
                source_id=experiment_id,
                state=status,
                previous_state=previous_state,
                payload=payload,
                error=error,
            )
        )
        if stage in (HookStage.COMPLETED, HookStage.FAILED, HookStage.CANCELLED):
            self._hook_manager.emit(
                HookContext(
                    hook_name=HookCatalog.EXPERIMENT_RUN,
                    stage=HookStage.FINALLY,
                    source_id=experiment_id,
                    state=status,
                    previous_state=previous_state,
                    payload=payload,
                    error=error,
                )
            )

    def create_and_start_on_branch(
            self,
            name: str,
            ticker_symbol: str,
            branch_id: str,
            commit_hash: str,
            triggered_by: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        current_weights = self._load_asset_strategy_weights(commit_hash, ticker_symbol)
        candidates: list[ExperimentCandidate] = [
            ExperimentCandidate(
                candidate_id="cand_current",
                name="Current Configuration",
                candidate_type=CandidateType.CURRENT_CONFIG,
                strategy_weights=dict(current_weights),
                description="AI-proposed configuration on forked branch",
            )
        ]
        if current_weights:
            candidates.append(
                ExperimentCandidate(
                    candidate_id="cand_equal_weight",
                    name="Equal-Weight Strategies",
                    candidate_type=CandidateType.EQUAL_WEIGHT,
                    strategy_weights={k: 1.0 for k in current_weights},
                    description="Equal weight baseline across all registered strategies",
                )
            )

        spec = ExperimentSpec(
            name=name,
            ticker_symbol=ticker_symbol,
            base_commit_hash=commit_hash,
            branch_id=branch_id,
            test_selection=TestSelection.BOTH,
            windows=WalkForwardWindowSpec(),
            candidates=candidates,
            triggered_by=triggered_by,
        )
        experiment_id = f"exp_{uuid.uuid4().hex[:12]}"
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            repo.save_experiment(
                experiment_id=experiment_id,
                name=name,
                ticker_symbol=ticker_symbol,
                branch_id=branch_id,
                base_commit_hash=commit_hash,
                status=ExperimentStatus.DRAFT.value,
                spec=spec.model_dump(mode="json"),
                run_bindings=[],
            )
        try:
            return self.start_experiment(experiment_id)
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.warning("Created experiment %s on branch %s but auto-start failed: %s", experiment_id, branch_id, exc)
            return self.get_experiment(experiment_id) or {"experiment_id": experiment_id, "branch_id": branch_id}

    def create_and_start_from_suggestion(
            self,
            suggestion: dict[str, Any],
            triggered_by: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ticker_symbol = str(suggestion.get("ticker_symbol") or "").strip()
        if not ticker_symbol:
            raise ValueError("Suggested experiment configuration must specify 'ticker_symbol'.")

        name = str(suggestion.get("name") or f"Suggested Experiment ({ticker_symbol})")[:80]
        base_commit = str(suggestion.get("base_commit_hash") or "").strip()
        if not base_commit:
            try:
                base_commit = self._vcs_service.resolve_commit_hash("refs/heads/main")
            except (CommitNotFoundError, InvalidReferenceError):
                base_commit = self._vcs_service.resolve_commit_hash("HEAD")

        branch_info = self._backtest_service.create_branch(
            name=f"exp-{name}",
            description=f"Agent-suggested experiment branch for {ticker_symbol}",
            source_commit_hash=base_commit,
            author="agent-experiment",
        )
        branch_id = branch_info["branch_id"]

        raw_candidates = suggestion.get("candidates") or []
        candidates = [
            ExperimentCandidate.model_validate(item)
            for item in raw_candidates
            if isinstance(item, dict)
        ]
        if not candidates:
            current_weights = self._load_asset_strategy_weights(base_commit, ticker_symbol)
            candidates = [
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current Configuration",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                    strategy_weights=dict(current_weights),
                )
            ]

        raw_data_source = suggestion.get("data_source")
        data_source = (
            BacktestMarketDataSpec.model_validate(raw_data_source)
            if isinstance(raw_data_source, dict)
            else BacktestMarketDataSpec()
        )
        raw_period = suggestion.get("period")
        period = (
            BacktestPeriodSpec.model_validate(raw_period)
            if isinstance(raw_period, dict)
            else None
        )
        raw_selection = suggestion.get("test_selection") or TestSelection.BOTH.value
        test_selection = TestSelection(raw_selection)
        raw_windows = suggestion.get("windows")
        windows = (
            WalkForwardWindowSpec.model_validate(raw_windows)
            if isinstance(raw_windows, dict)
            else (
                WalkForwardWindowSpec()
                if test_selection in (TestSelection.WALK_FORWARD_ONLY, TestSelection.BOTH)
                else None
            )
        )

        spec = ExperimentSpec(
            name=name,
            ticker_symbol=ticker_symbol,
            base_commit_hash=base_commit,
            branch_id=branch_id,
            test_selection=test_selection,
            data_source=data_source,
            period=period,
            windows=windows,
            candidates=candidates,
            triggered_by=triggered_by,
        )
        experiment_id = f"exp_{uuid.uuid4().hex[:12]}"
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            repo.save_experiment(
                experiment_id=experiment_id,
                name=name,
                ticker_symbol=ticker_symbol,
                branch_id=branch_id,
                base_commit_hash=base_commit,
                status=ExperimentStatus.DRAFT.value,
                spec=spec.model_dump(mode="json"),
                run_bindings=[],
            )
        try:
            return self.start_experiment(experiment_id)
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.warning(
                "Created suggested experiment %s on branch %s but auto-start failed: %s",
                experiment_id,
                branch_id,
                exc,
            )
            return self.get_experiment(experiment_id) or {
                "experiment_id": experiment_id,
                "branch_id": branch_id,
            }

    def repoint_and_rerun(
            self,
            experiment_id: str,
            branch_id: str,
            commit_hash: str,
    ) -> dict[str, Any]:
        existing = self.get_experiment(experiment_id)
        if not existing:
            raise ValueError(f"Experiment '{experiment_id}' not found.")

        ticker_symbol = existing["ticker_symbol"]
        spec_dict = dict(existing.get("spec") or {})
        spec_dict["branch_id"] = branch_id
        spec_dict["base_commit_hash"] = commit_hash
        if spec_dict.get("test_selection") in (None, TestSelection.BACKTEST_ONLY.value):
            spec_dict["test_selection"] = TestSelection.BOTH.value
        if not spec_dict.get("windows"):
            spec_dict["windows"] = WalkForwardWindowSpec().model_dump(mode="json")
        current_weights = self._load_asset_strategy_weights(commit_hash, ticker_symbol)
        for cand in spec_dict.get("candidates", []):
            if cand.get("candidate_id") == "cand_current":
                cand["strategy_weights"] = dict(current_weights)

        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            repo.save_experiment(
                experiment_id=experiment_id,
                name=existing["name"],
                ticker_symbol=ticker_symbol,
                branch_id=branch_id,
                base_commit_hash=commit_hash,
                status=ExperimentStatus.DRAFT.value,
                spec=spec_dict,
                run_bindings=[],
                report=None,
            )
        try:
            return self.start_experiment(experiment_id)
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.warning("Repointed experiment %s to branch %s but auto-rerun failed: %s", experiment_id, branch_id, exc)
            return self.get_experiment(experiment_id) or existing

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

        windows = req.windows
        if (
            req.test_selection in (TestSelection.WALK_FORWARD_ONLY, TestSelection.BOTH)
            and windows is None
        ):
            windows = WalkForwardWindowSpec()

        spec = ExperimentSpec(
            name=req.name,
            ticker_symbol=req.ticker_symbol,
            base_commit_hash=base_commit,
            branch_id=branch_id,
            test_selection=req.test_selection,
            data_source=req.data_source,
            period=req.period,
            windows=windows,
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
            "run_history": [],
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

    @staticmethod
    def _build_config_snapshot(spec: ExperimentSpec) -> dict[str, Any]:
        return ExperimentRunConfigSnapshot(
            data_source=spec.data_source,
            period=spec.period,
            windows=spec.windows,
            initial_balance=spec.initial_balance,
            execution=spec.execution,
        ).model_dump(mode="json")

    @staticmethod
    def _normalize_shared_config(config: dict[str, Any]) -> dict[str, Any]:
        ds = dict(config.get("data_source") or {})
        source_type = str(ds.get("source_type") or "")
        normalized_ds: dict[str, Any] = {
            "source_type": source_type,
            "path": ds.get("path"),
        }
        if source_type == "csv":
            normalized_ds["dataset_id"] = ds.get("dataset_id")
        return {
            "data_source": normalized_ds,
            "period": config.get("period"),
            "initial_balance": str(config.get("initial_balance") or ""),
            "execution": config.get("execution") or {},
        }

    @classmethod
    def _compute_staleness(
            cls,
            leg_configs: dict[str, Any],
            latest_config: dict[str, Any],
    ) -> tuple[dict[str, bool], dict[str, list[str]]]:
        latest_shared = cls._normalize_shared_config(latest_config)
        stale_legs: dict[str, bool] = {}
        stale_reasons: dict[str, list[str]] = {}
        for leg in ("backtest", "walk_forward"):
            leg_cfg = leg_configs.get(leg)
            if not isinstance(leg_cfg, dict):
                stale_legs[leg] = False
                stale_reasons[leg] = []
                continue
            leg_shared = cls._normalize_shared_config(leg_cfg)
            diffs = [
                field
                for field in ("data_source", "period", "initial_balance", "execution")
                if leg_shared.get(field) != latest_shared.get(field)
            ]
            stale_legs[leg] = bool(diffs)
            stale_reasons[leg] = diffs
        return stale_legs, stale_reasons

    @staticmethod
    def _apply_start_overrides(
            spec: ExperimentSpec,
            effective_selection: TestSelection,
            config_overrides: Optional[StartExperimentRequest],
    ) -> None:
        data_or_period_changed = False
        if config_overrides is not None:
            if config_overrides.data_source is not None:
                spec.data_source = config_overrides.data_source
                data_or_period_changed = True
            if "period" in config_overrides.model_fields_set:
                spec.period = config_overrides.period
                data_or_period_changed = True
            if "windows" in config_overrides.model_fields_set:
                spec.windows = config_overrides.windows
            if config_overrides.initial_balance is not None:
                spec.initial_balance = config_overrides.initial_balance
            if config_overrides.execution is not None:
                spec.execution = config_overrides.execution

        if (
            data_or_period_changed
            and spec.data_source.source_type.value in ("market_data", "recorded_market_data")
            and (
                config_overrides is None
                or config_overrides.data_source is None
                or not config_overrides.data_source.dataset_id
            )
        ):
            spec.data_source = spec.data_source.model_copy(update={"dataset_id": None})

        if (
            effective_selection in (TestSelection.WALK_FORWARD_ONLY, TestSelection.BOTH)
            and spec.windows is None
        ):
            spec.windows = WalkForwardWindowSpec()

    def start_experiment(
            self,
            experiment_id: str,
            test_selection: Optional[TestSelection] = None,
            config_overrides: Optional[StartExperimentRequest] = None,
    ) -> dict[str, Any]:
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

            previous_status = exp["status"]
            prior_bindings = list(exp.get("run_bindings") or [])
            prior_report = exp.get("report") if isinstance(exp.get("report"), dict) else {}
            prior_leg_configs = (
                dict(prior_report.get("leg_configs") or {})
                if isinstance(prior_report.get("leg_configs"), dict)
                else {}
            )

            spec = ExperimentSpec.model_validate(exp["spec"])
            if not prior_leg_configs and prior_bindings:
                legacy_cfg = self._build_config_snapshot(spec)
                if any(b.get("backtest_session_id") for b in prior_bindings):
                    prior_leg_configs["backtest"] = legacy_cfg
                if any(b.get("walk_forward_run_id") for b in prior_bindings):
                    prior_leg_configs["walk_forward"] = legacy_cfg

            effective_selection = (
                config_overrides.test_selection
                if config_overrides is not None and config_overrides.test_selection is not None
                else (test_selection if test_selection is not None else spec.test_selection)
            )
            preserve_other = (
                config_overrides.preserve_other_results
                if config_overrides is not None
                else True
            )

            self._apply_start_overrides(spec, effective_selection, config_overrides)

            for cand in spec.candidates:
                cand.candidate_commit_hash = None

            bindings = self._dispatch_candidate_runs(
                spec,
                spec.candidates,
                run_selection=effective_selection,
                previous_bindings=prior_bindings if preserve_other else None,
            )

            has_bt = any(b.get("backtest_session_id") for b in bindings)
            has_wf = any(b.get("walk_forward_run_id") for b in bindings)
            if has_bt and has_wf:
                spec.test_selection = TestSelection.BOTH
            else:
                spec.test_selection = effective_selection

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

        self._active_run_meta[experiment_id] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "run_selection": effective_selection,
            "prior_leg_configs": prior_leg_configs,
            "config_snapshot": self._build_config_snapshot(spec),
        }
        cancel_evt = threading.Event()
        self._cancellation_events[experiment_id] = cancel_evt
        self._emit_experiment_hook(
            stage=HookStage.STARTED,
            experiment_id=experiment_id,
            spec=spec,
            status=ExperimentStatus.RUNNING.value,
            previous_state=previous_status,
        )
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

        cancelled_spec: Optional[ExperimentSpec] = None
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            exp = repo.get_experiment(experiment_id)
            if not exp:
                return False
            bindings = exp.get("run_bindings", [])
            for b in bindings:
                if b.get("status") in ("QUEUED", "RUNNING"):
                    b["status"] = "CANCELLED"
                wf_id = b.get("walk_forward_run_id")
                if wf_id and self._walk_forward_app_service:
                    try:
                        self._walk_forward_app_service.cancel_run(wf_id, reason="Cancelled via experiment")
                    except Exception:
                        pass
            repo.update_bindings(experiment_id, bindings)
            repo.update_status(experiment_id, ExperimentStatus.CANCELLED.value)
            if exp.get("spec"):
                cancelled_spec = ExperimentSpec.model_validate(exp["spec"])
        if cancelled_spec is not None:
            self._emit_experiment_hook(
                stage=HookStage.CANCELLED,
                experiment_id=experiment_id,
                spec=cancelled_spec,
                status=ExperimentStatus.CANCELLED.value,
                previous_state=ExperimentStatus.RUNNING.value,
            )
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
        self._emit_experiment_hook(
            stage=HookStage.STARTED,
            experiment_id=experiment_id,
            spec=spec,
            status=ExperimentStatus.RUNNING.value,
            previous_state=ExperimentStatus.DRAFT.value,
        )
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
            enabled_strats = [s for s in strategies if s.enabled]
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

        if cand.candidate_type == CandidateType.CUSTOM_COMBINATION:
            updated = list(strategies)
            existing_names = {s.name for s in updated if s.name}
            for raw_strategy in cand.strategies_to_add:
                parsed = StrategyConfig.model_validate(raw_strategy)
                if parsed.name and parsed.name not in existing_names:
                    updated.append(parsed)
                    existing_names.add(parsed.name)
            if cand.strategy_enabled_overrides:
                updated = [
                    s.model_copy(update={"enabled": bool(cand.strategy_enabled_overrides[s.name])})
                    if s.name and s.name in cand.strategy_enabled_overrides
                    else s
                    for s in updated
                ]
            if cand.strategy_weights:
                updated = [
                    s.model_copy(update={"weight": float(cand.strategy_weights[s.name])})
                    if s.name and s.name in cand.strategy_weights
                    else s
                    for s in updated
                ]
            msg = f"Experiment candidate variant: {cand.name} ({cand.candidate_id})"
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
                    if s.name and s.enabled
                }
        except Exception:  # pylint: disable=broad-except
            pass
        return {}

    def _resolve_candidate_commit(
            self,
            branch_id: str,
            ticker_symbol: str,
            cand: ExperimentCandidate,
            base_commit_hash: Optional[str] = None,
    ) -> str:
        if cand.candidate_commit_hash:
            return cand.candidate_commit_hash

        branch_ref = f"refs/heads/backtest/{branch_id}"
        head_commit = base_commit_hash or self._vcs_service.resolve_commit_hash(branch_ref)

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

            if matched_asset and (matched_asset.strategies or cand.strategies_to_add):
                variant_update = self._apply_candidate_weights(
                    cand, list(matched_asset.strategies or [])
                )
                if variant_update:
                    updated_strats, commit_msg = variant_update
                    asset_updates: dict[str, Any] = {"strategies": updated_strats}
                    if cand.consensus_override and matched_asset.consensus is not None:
                        consensus_updates = {
                            k: float(v)
                            for k, v in cand.consensus_override.items()
                            if k in ("buy", "sell")
                        }
                        if consensus_updates:
                            asset_updates["consensus"] = matched_asset.consensus.model_copy(
                                update=consensus_updates
                            )
                    updated_asset = replace(matched_asset, **asset_updates)
                    updated_assets = [
                        updated_asset if a.ticker_symbol == ticker_symbol else a
                        for a in trading_config.assets
                    ]
                    updated_config = trading_config.model_copy(update={"assets": updated_assets})
                    candidate_ref = f"refs/experiments/{branch_id}/{cand.candidate_id}"
                    self._vcs_service.branch(candidate_ref, from_ref=head_commit)
                    commit = self._vcs_service.commit(
                        content=updated_config,
                        author="experiment-service",
                        message=commit_msg,
                        ref=candidate_ref,
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

    def _pin_data_source(
            self,
            spec: ExperimentSpec,
            runner_service: Optional[BacktestApplicationService | WalkForwardApplicationService],
    ) -> BacktestMarketDataSpec:
        if (
            runner_service is None
            or spec.data_source.dataset_id
            or spec.data_source.source_type.value not in ("market_data", "recorded_market_data")
        ):
            return spec.data_source
        snapshot_id = runner_service.pin_market_data_snapshot(
            ticker_symbol=spec.ticker_symbol,
            start_time=spec.period.start_time if spec.period else None,
            end_time=spec.period.end_time if spec.period else None,
        )
        if isinstance(snapshot_id, str) and snapshot_id:
            return spec.data_source.model_copy(update={"dataset_id": snapshot_id})
        return spec.data_source

    def _dispatch_candidate_runs(
            self,
            spec: ExperimentSpec,
            candidates: list[ExperimentCandidate],
            run_selection: Optional[TestSelection] = None,
            previous_bindings: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        bindings: list[dict[str, Any]] = []
        branch_ref = f"refs/heads/backtest/{spec.branch_id}"
        base_commit_hash = self._vcs_service.resolve_commit_hash(branch_ref)

        selection = run_selection or spec.test_selection
        run_bt = selection in (TestSelection.BACKTEST_ONLY, TestSelection.BOTH)
        run_wf = selection in (TestSelection.WALK_FORWARD_ONLY, TestSelection.BOTH)
        prev_by_cid = {
            str(b.get("candidate_id")): b
            for b in (previous_bindings or [])
            if isinstance(b, dict) and b.get("candidate_id")
        }

        pin_runner = (
            self._backtest_app_service
            if (run_bt and self._backtest_app_service is not None)
            else self._walk_forward_app_service
        )
        pinned_data_source = (
            self._pin_data_source(spec, pin_runner)
            if (run_bt or run_wf)
            else spec.data_source
        )

        for cand in candidates:
            commit_hash = self._resolve_candidate_commit(
                spec.branch_id,
                spec.ticker_symbol,
                cand,
                base_commit_hash=base_commit_hash,
            )
            prev = prev_by_cid.get(cand.candidate_id, {})
            bt_session_id: Optional[str] = None
            bt_status: Optional[str] = None
            bt_error: Optional[str] = None
            wf_run_id: Optional[str] = None
            wf_status: Optional[str] = None
            wf_error: Optional[str] = None

            if run_bt:
                if self._backtest_app_service:
                    bt_spec = BacktestRunSpec(
                        ticker_symbol=spec.ticker_symbol,
                        configuration=BacktestConfigurationSpec(
                            source_type=BacktestConfigurationSourceType.VCS,
                            vcs_commit_hash=commit_hash,
                        ),
                        data_source=pinned_data_source,
                        period=spec.period,
                        initial_balance=spec.initial_balance,
                        execution=spec.execution,
                    )
                    bt_session = self._backtest_app_service.start_backtest_run(bt_spec)
                    bt_session_id = bt_session.id
                    bt_status = "RUNNING"
            elif prev.get("backtest_session_id"):
                bt_session_id = prev.get("backtest_session_id")
                bt_status = prev.get("backtest_status") or "COMPLETED"
                bt_error = prev.get("backtest_error")

            if run_wf:
                if self._walk_forward_app_service:
                    wf_spec = WalkForwardRunSpec(
                        ticker_symbol=spec.ticker_symbol,
                        configuration=BacktestConfigurationSpec(
                            source_type=BacktestConfigurationSourceType.VCS,
                            vcs_commit_hash=commit_hash,
                        ),
                        data_source=pinned_data_source,
                        period=spec.period,
                        windows=spec.windows or WalkForwardWindowSpec(),
                        initial_balance=spec.initial_balance,
                        execution=spec.execution,
                        candidate_weights=cand.strategy_weights if cand.strategy_weights else None,
                    )
                    wf_run = self._walk_forward_app_service.start_run(wf_spec)
                    wf_run_id = wf_run["run_id"]
                    wf_status = "RUNNING"
            elif prev.get("walk_forward_run_id"):
                wf_run_id = prev.get("walk_forward_run_id")
                wf_status = prev.get("walk_forward_status") or "COMPLETED"
                wf_error = prev.get("walk_forward_error")

            bindings.append({
                "candidate_id": cand.candidate_id,
                "backtest_session_id": bt_session_id,
                "walk_forward_run_id": wf_run_id,
                "backtest_status": bt_status,
                "backtest_error": bt_error,
                "walk_forward_status": wf_status,
                "walk_forward_error": wf_error,
                "status": "RUNNING",
                "error": None,
            })

        return bindings

    def _watch_experiment_runs(self, experiment_id: str) -> None:  # pylint: disable=too-many-locals
        cancel_evt = self._cancellation_events.get(experiment_id)
        finished_spec: Optional[ExperimentSpec] = None
        finished_status = ""
        finished_report: Optional[dict[str, Any]] = None
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
                    if b.get("status") in ("COMPLETED", "PARTIAL", "FAILED", "CANCELLED"):
                        continue

                    bt_done, wf_done, leg_changed = self._poll_binding_status(uow, b)
                    if leg_changed:
                        updated = True

                    if bt_done and wf_done:
                        active_statuses = [
                            s
                            for s in (b.get("backtest_status"), b.get("walk_forward_status"))
                            if s is not None
                        ]
                        leg_errors = [
                            e
                            for e in (b.get("backtest_error"), b.get("walk_forward_error"))
                            if e
                        ]
                        if not active_statuses or all(s == "COMPLETED" for s in active_statuses):
                            b["status"] = "COMPLETED"
                            b["error"] = None
                        elif any(s == "COMPLETED" for s in active_statuses):
                            b["status"] = "PARTIAL"
                            b["error"] = "; ".join(leg_errors) if leg_errors else None
                        else:
                            b["status"] = "FAILED"
                            b["error"] = "; ".join(leg_errors) if leg_errors else "Evaluation failed"
                            any_failed = True
                        updated = True
                    else:
                        all_done = False

                if updated:
                    repo.update_bindings(experiment_id, bindings)

                if all_done:
                    spec_dict = exp.get("spec", {})
                    spec = ExperimentSpec.model_validate(spec_dict)
                    repo.update_status(experiment_id, ExperimentStatus.AGGREGATING.value)
                    self._emit_experiment_hook(
                        stage=HookStage.STATE_CHANGED,
                        experiment_id=experiment_id,
                        spec=spec,
                        status=ExperimentStatus.AGGREGATING.value,
                        previous_state=ExperimentStatus.RUNNING.value,
                    )
                    run_meta = self._active_run_meta.pop(experiment_id, {})
                    run_selection = run_meta.get("run_selection") or spec.test_selection
                    prior_leg_configs = dict(run_meta.get("prior_leg_configs") or {})
                    config_snapshot = run_meta.get("config_snapshot") or self._build_config_snapshot(spec)

                    leg_configs = dict(prior_leg_configs)
                    if run_selection in (TestSelection.BACKTEST_ONLY, TestSelection.BOTH):
                        leg_configs["backtest"] = config_snapshot
                    if run_selection in (TestSelection.WALK_FORWARD_ONLY, TestSelection.BOTH):
                        leg_configs["walk_forward"] = config_snapshot
                    stale_legs, stale_reasons = self._compute_staleness(leg_configs, config_snapshot)

                    report = self._compute_experiment_report(
                        uow,
                        spec,
                        bindings,
                        self._vcs_service,
                        last_run_selection=run_selection,
                        leg_configs=leg_configs,
                        stale_legs=stale_legs,
                        stale_reasons=stale_reasons,
                    )
                    final_status = (
                        ExperimentStatus.FAILED.value
                        if (any_failed and all(b.get("status") == "FAILED" for b in bindings))
                        else ExperimentStatus.COMPLETED.value
                    )
                    existing_history = list(exp.get("run_history") or [])
                    history_entry = self._build_run_history_entry(
                        run_number=len(existing_history) + 1,
                        started_at=str(run_meta.get("started_at") or datetime.now(timezone.utc).isoformat()),
                        test_selection=run_selection,
                        status=final_status,
                        config_snapshot=config_snapshot,
                        report=report,
                    )
                    existing_history.append(history_entry)
                    repo.update_report(
                        experiment_id,
                        final_status,
                        report,
                        run_history=existing_history,
                    )
                    self.app_logger.info("Experiment %s finished with status %s", experiment_id, final_status)
                    finished_spec = spec
                    finished_status = final_status
                    finished_report = report
                    break

        if finished_spec is not None:
            terminal_stage = (
                HookStage.FAILED
                if finished_status == ExperimentStatus.FAILED.value
                else HookStage.COMPLETED
            )
            self._emit_experiment_hook(
                stage=terminal_stage,
                experiment_id=experiment_id,
                spec=finished_spec,
                status=finished_status,
                previous_state=ExperimentStatus.AGGREGATING.value,
                report=finished_report,
            )
            completed_symbol = (
                finished_spec.ticker_symbol
                if finished_status == ExperimentStatus.COMPLETED.value
                else None
            )
            completed_commit = finished_spec.base_commit_hash
            if completed_symbol and self._on_experiment_completed is not None:
                try:
                    self._on_experiment_completed(completed_symbol, completed_commit)
                except Exception as exc:  # pylint: disable=broad-except
                    self.app_logger.warning(
                        "Post-experiment drift hook failed for %s: %s",
                        completed_symbol,
                        exc,
                    )

    @staticmethod
    def _build_run_history_entry(  # pylint: disable=too-many-arguments
            run_number: int,
            started_at: str,
            test_selection: TestSelection,
            status: str,
            config_snapshot: dict[str, Any],
            report: dict[str, Any],
    ) -> dict[str, Any]:
        candidate_summaries: dict[str, Any] = {}
        for cid, entry in (report.get("candidates") or {}).items():
            if not isinstance(entry, dict):
                continue
            bt = entry.get("backtest") if isinstance(entry.get("backtest"), dict) else None
            wf = entry.get("walk_forward") if isinstance(entry.get("walk_forward"), dict) else None
            candidate_summaries[cid] = {
                "name": entry.get("name") or cid,
                "status": entry.get("status"),
                "backtest_status": entry.get("backtest_status"),
                "walk_forward_status": entry.get("walk_forward_status"),
                "backtest_return_pct": bt.get("percentage_return") if bt else None,
                "backtest_total_trades": bt.get("total_trades") if bt else None,
                "walk_forward_oos_return_pct": (
                    wf.get("aggregate_oos_return_pct")
                    if wf and wf.get("aggregate_oos_return_pct") is not None
                    else (wf.get("out_of_sample_return_pct") if wf else None)
                ),
                "walk_forward_wfe": (
                    wf.get("walk_forward_efficiency_ratio")
                    if wf and wf.get("walk_forward_efficiency_ratio") is not None
                    else (wf.get("walk_forward_efficiency") if wf else None)
                ),
                "walk_forward_stability": wf.get("stability_classification") if wf else None,
            }
        return ExperimentRunHistoryEntry(
            run_number=run_number,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            test_selection=test_selection,
            status=status,
            config=ExperimentRunConfigSnapshot.model_validate(config_snapshot),
            candidate_summaries=candidate_summaries,
        ).model_dump(mode="json")

    @staticmethod
    def _poll_binding_status(uow: Any, b: dict[str, Any]) -> tuple[bool, bool, bool]:
        bt_done = True
        wf_done = True
        changed = False

        if b.get("backtest_session_id"):
            if b.get("backtest_status") in ("COMPLETED", "FAILED", "CANCELLED"):
                bt_done = True
            else:
                bt_repo = uow.get_repository(PostgresBacktestRepository)
                bt_session = bt_repo.get_session(b["backtest_session_id"])
                if bt_session:
                    status_str = (
                        bt_session.status.value
                        if isinstance(bt_session.status, Enum)
                        else str(bt_session.status)
                    )
                    if status_str in ("QUEUED", "RUNNING"):
                        bt_done = False
                    elif status_str == "FAILED":
                        b["backtest_status"] = "FAILED"
                        b["backtest_error"] = (
                            getattr(bt_session, "error_message", None)
                            or getattr(bt_session, "error", None)
                            or "Backtest run failed"
                        )
                        changed = True
                    elif status_str == "CANCELLED":
                        b["backtest_status"] = "CANCELLED"
                        b["backtest_error"] = bt_session.error_message or "Backtest run was cancelled"
                        changed = True
                    else:
                        b["backtest_status"] = "COMPLETED"
                        b["backtest_error"] = None
                        changed = True
                else:
                    bt_done = False

        if b.get("walk_forward_run_id"):
            if b.get("walk_forward_status") in ("COMPLETED", "FAILED", "CANCELLED"):
                wf_done = True
            else:
                wf_repo = uow.get_repository(PostgresWalkForwardRepository)
                wf_run = wf_repo.get_run(b["walk_forward_run_id"])
                if wf_run:
                    wf_status = wf_run.get("status")
                    if wf_status in ("QUEUED", "RUNNING"):
                        wf_done = False
                    elif wf_status == "FAILED":
                        b["walk_forward_status"] = "FAILED"
                        summary = wf_run.get("summary") if isinstance(wf_run.get("summary"), dict) else {}
                        b["walk_forward_error"] = (
                            wf_run.get("error_message")
                            or summary.get("error_message")
                            or summary.get("error")
                            or "Walk-forward run failed"
                        )
                        changed = True
                    elif wf_status == "CANCELLED":
                        b["walk_forward_status"] = "CANCELLED"
                        b["walk_forward_error"] = (
                            wf_run.get("error_message") or "Walk-forward run was cancelled"
                        )
                        changed = True
                    else:
                        b["walk_forward_status"] = "COMPLETED"
                        b["walk_forward_error"] = None
                        changed = True
                else:
                    wf_done = False

        return bt_done, wf_done, changed

    @classmethod
    def _compute_experiment_report(  # pylint: disable=too-many-locals,too-many-arguments
            cls,
            uow: Any,
            spec: ExperimentSpec,
            bindings: list[dict[str, Any]],
            vcs_service: Optional[VCSService] = None,
            last_run_selection: Optional[TestSelection] = None,
            leg_configs: Optional[dict[str, Any]] = None,
            stale_legs: Optional[dict[str, bool]] = None,
            stale_reasons: Optional[dict[str, list[str]]] = None,
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
                "backtest_status": b.get("backtest_status"),
                "backtest_error": b.get("backtest_error"),
                "walk_forward_status": b.get("walk_forward_status"),
                "walk_forward_error": b.get("walk_forward_error"),
                "backtest": None,
                "walk_forward": None,
            }

            if b.get("backtest_session_id") and b.get("backtest_status") not in ("FAILED", "CANCELLED"):
                metrics = bt_repo.get_result_metrics(b["backtest_session_id"])
                cand_entry["backtest"] = metrics
                if cid == "cand_current" and metrics:
                    baseline_bt_ret = float(metrics.get("percentage_return", 0.0))

            if b.get("walk_forward_run_id") and b.get("walk_forward_status") not in ("FAILED", "CANCELLED"):
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
        completed_cands = sum(1 for b in bindings if b.get("status") in ("COMPLETED", "PARTIAL"))
        partial_cands = sum(1 for b in bindings if b.get("status") == "PARTIAL")
        strat_attr, combo_matrix, strat_actions, strat_weights, strat_regime, regime_attr = (
            cls._extract_strategy_matrices(
                candidate_reports, spec=spec, vcs_service=vcs_service
            )
        )

        evaluation_context = cls._build_evaluation_context(
            spec=spec,
            candidate_reports=candidate_reports,
            vcs_service=vcs_service,
        )

        return {
            "summary": {
                "total_candidates": total_cands,
                "completed_candidates": completed_cands,
                "partial_candidates": partial_cands,
                "failed_candidates": total_cands - completed_cands,
                "test_selection": spec.test_selection.value,
                "last_run_selection": (last_run_selection or spec.test_selection).value,
            },
            "leg_configs": leg_configs or {},
            "stale_legs": stale_legs or {"backtest": False, "walk_forward": False},
            "stale_reasons": stale_reasons or {"backtest": [], "walk_forward": []},
            "evaluation_context": evaluation_context,
            "candidates": candidate_reports,
            "strategy_attribution": strat_attr,
            "strategy_combination_matrix": combo_matrix,
            "strategy_actions": strat_actions,
            "strategy_weights": strat_weights,
            "strategy_regime_matrix": strat_regime,
            "regime_attribution": regime_attr,
        }

    @classmethod
    def _build_evaluation_context(  # pylint: disable=too-many-locals
            cls,
            spec: ExperimentSpec,
            candidate_reports: dict[str, Any],
            vcs_service: Optional[VCSService] = None,
    ) -> dict[str, Any]:
        dataset_ctx = cls._extract_dataset_context(spec, candidate_reports, vcs_service)
        regime_ctx = cls._extract_regime_context(candidate_reports)
        risk_ctx = cls._extract_risk_block_context(candidate_reports)
        return {
            "dataset": dataset_ctx,
            "market_regime": regime_ctx,
            "portfolio_risk_blocks": risk_ctx,
        }

    @classmethod
    def _extract_dataset_context(
            cls,
            spec: ExperimentSpec,
            candidate_reports: dict[str, Any],
            vcs_service: Optional[VCSService],
    ) -> dict[str, Any]:
        bar_count: Optional[int] = None
        start_time: Optional[str] = (
            spec.period.start_time.isoformat()
            if spec.period and spec.period.start_time
            else None
        )
        end_time: Optional[str] = (
            spec.period.end_time.isoformat()
            if spec.period and spec.period.end_time
            else None
        )
        duration_seconds: Optional[float] = None

        for cid in ("cand_current", *candidate_reports.keys()):
            bt = (candidate_reports.get(cid) or {}).get("backtest")
            if not isinstance(bt, dict):
                continue
            ds = bt.get("dataset_context")
            if isinstance(ds, dict) and ds.get("bar_count") is not None:
                bar_count = int(ds["bar_count"])
                start_time = ds.get("start_time") or start_time
                end_time = ds.get("end_time") or end_time
                duration_seconds = ds.get("duration_seconds")
                break

        timeframe = cls._resolve_asset_timeframe(spec, vcs_service)
        source_type = (
            spec.data_source.source_type.value
            if isinstance(spec.data_source.source_type, Enum)
            else str(spec.data_source.source_type)
        )
        return {
            "bar_count": bar_count,
            "timeframe": timeframe,
            "source_type": source_type,
            "dataset_id": spec.data_source.dataset_id,
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": duration_seconds,
        }

    @classmethod
    def _resolve_asset_timeframe(
            cls,
            spec: ExperimentSpec,
            vcs_service: Optional[VCSService],
    ) -> Optional[str]:
        commit_hash = cls._resolve_target_commit(spec, vcs_service)
        if not commit_hash or vcs_service is None:
            return None
        try:
            raw_config = vcs_service.checkout(commit_hash)
            trading_config = TradingConfig.model_validate(raw_config)
            matched = next(
                (a for a in trading_config.assets if a.ticker_symbol == spec.ticker_symbol),
                None,
            )
            if matched and matched.candles_timeframe is not None:
                return (
                    matched.candles_timeframe.value
                    if isinstance(matched.candles_timeframe, Enum)
                    else str(matched.candles_timeframe)
                )
        except Exception:  # pylint: disable=broad-except
            pass
        return None

    @staticmethod
    def _extract_regime_context(
            candidate_reports: dict[str, Any],
    ) -> dict[str, Any]:
        regime_counts: dict[str, int] = {}
        for cid in ("cand_current", *candidate_reports.keys()):
            bt = (candidate_reports.get(cid) or {}).get("backtest")
            if not isinstance(bt, dict):
                continue
            counts = bt.get("regime_counts")
            if isinstance(counts, dict) and counts:
                regime_counts = {str(k): int(v) for k, v in counts.items() if int(v) > 0}
                break

        total_obs = sum(regime_counts.values())
        if total_obs <= 0:
            return {
                "dominant": None,
                "total_observations": 0,
                "distribution": [],
            }

        ordered = sorted(regime_counts.items(), key=lambda item: (-item[1], item[0]))
        distribution = [
            {
                "regime": regime,
                "count": count,
                "pct": round((count / total_obs) * 100.0, 1),
            }
            for regime, count in ordered
        ]
        return {
            "dominant": ordered[0][0],
            "total_observations": total_obs,
            "distribution": distribution,
        }

    @classmethod
    def _extract_risk_block_context(
            cls,
            candidate_reports: dict[str, Any],
    ) -> dict[str, Any]:
        baseline_bt = (candidate_reports.get("cand_current") or {}).get("backtest")
        baseline_diag = (
            baseline_bt.get("signal_diagnostics")
            if isinstance(baseline_bt, dict)
            else None
        )
        baseline_summary = cls._summarize_signal_diagnostics(
            baseline_diag if isinstance(baseline_diag, dict) else {}
        )

        total_signals = 0
        total_blocked = 0
        merged_reasons: dict[str, int] = {}
        for entry in candidate_reports.values():
            bt = entry.get("backtest") if isinstance(entry, dict) else None
            diag = bt.get("signal_diagnostics") if isinstance(bt, dict) else None
            if not isinstance(diag, dict):
                continue
            total_signals += int(diag.get("total_signals") or 0)
            total_blocked += int(diag.get("risk_blocked_signals") or 0)
            for reason, cnt in (diag.get("risk_block_reasons") or {}).items():
                merged_reasons[str(reason)] = merged_reasons.get(str(reason), 0) + int(cnt)

        all_summary = cls._summarize_signal_diagnostics(
            {
                "total_signals": total_signals,
                "risk_blocked_signals": total_blocked,
                "risk_block_reasons": merged_reasons,
            }
        )
        return {
            "baseline": baseline_summary,
            "all_candidates": all_summary,
        }

    @staticmethod
    def _summarize_signal_diagnostics(diag: dict[str, Any]) -> dict[str, Any]:
        total = int(diag.get("total_signals") or 0)
        blocked = int(diag.get("risk_blocked_signals") or 0)
        blocked_pct = round((blocked / total) * 100.0, 1) if total > 0 else None
        reasons_raw = diag.get("risk_block_reasons") or {}
        top_reasons = [
            {"reason": str(reason), "count": int(cnt)}
            for reason, cnt in sorted(
                reasons_raw.items(), key=lambda item: (-int(item[1]), str(item[0]))
            )[:4]
            if int(cnt) > 0
        ]
        return {
            "total_signals": total,
            "blocked_signals": blocked,
            "blocked_pct": blocked_pct,
            "top_reasons": top_reasons,
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
                        if s.name and s.enabled:
                            action_val = s.action.value if s.action else "BUY"
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
