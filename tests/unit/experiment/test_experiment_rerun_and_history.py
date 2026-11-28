from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from api.interfaces.backtest_run_spec import (
    BacktestDataSourceType,
    BacktestExecutionSpec,
    BacktestMarketDataSpec,
)
from api.interfaces.experiment import (
    CandidateType,
    ExperimentCandidate,
    ExperimentSpec,
    ExperimentStatus,
    StartExperimentRequest,
    TestSelection,
)
from api.interfaces.walk_forward import WalkForwardWindowSpec, WindowMode
from src.agent.automation.experiment_completion_handler import (
    ExperimentCompletionAgentHandler,
)
from src.server.services.experiment_application_service import (
    ExperimentApplicationService,
)


class TestExperimentWalkForwardAndReruns:  # pylint: disable=attribute-defined-outside-init,protected-access
    def setup_method(self) -> None:
        self.mock_db = MagicMock()
        self.mock_uow = MagicMock()
        self.mock_db.get_unit_of_work.return_value.__enter__.return_value = self.mock_uow
        self.mock_repo = MagicMock()
        self.mock_uow.get_repository.return_value = self.mock_repo

        self.mock_vcs = MagicMock()
        self.mock_vcs.resolve_commit_hash.return_value = "commit_sha_base_001"

        self.mock_backtest_service = MagicMock()
        self.mock_backtest_service.create_branch.return_value = {"branch_id": "exp-branch-1"}
        self.mock_bt_app = MagicMock()
        self.mock_wf_app = MagicMock()

        self.service = ExperimentApplicationService(
            db_manager=self.mock_db,
            vcs_service=self.mock_vcs,
            backtest_service=self.mock_backtest_service,
            backtest_app_service=self.mock_bt_app,
            walk_forward_app_service=self.mock_wf_app,
        )

    def test_create_and_start_on_branch_defaults_to_both_with_windows(self) -> None:
        self.mock_repo.get_experiment.return_value = None
        with patch.object(self.service, "start_experiment", return_value={"status": "RUNNING"}):
            self.service.create_and_start_on_branch(
                name="Branch Study",
                ticker_symbol="BTC_USD",
                branch_id="exp-branch-1",
                commit_hash="commit_sha_base_001",
            )
        saved_spec = self.mock_repo.save_experiment.call_args[1]["spec"]
        assert saved_spec["test_selection"] == TestSelection.BOTH.value
        assert saved_spec["windows"] is not None

    def test_create_and_start_from_suggestion_defaults_to_both(self) -> None:
        with patch.object(self.service, "start_experiment", return_value={"status": "RUNNING"}):
            self.service.create_and_start_from_suggestion(
                suggestion={
                    "name": "No Signals Study",
                    "ticker_symbol": "ETH_USD",
                }
            )
        saved_spec = self.mock_repo.save_experiment.call_args[1]["spec"]
        assert saved_spec["test_selection"] == TestSelection.BOTH.value
        assert saved_spec["windows"] is not None

    def test_repoint_and_rerun_upgrades_legacy_backtest_only_to_both(self) -> None:
        self.mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_legacy",
            "name": "Legacy",
            "ticker_symbol": "BTC_USD",
            "branch_id": "old-branch",
            "base_commit_hash": "old_commit",
            "status": "COMPLETED",
            "spec": {
                "name": "Legacy",
                "ticker_symbol": "BTC_USD",
                "branch_id": "old-branch",
                "base_commit_hash": "old_commit",
                "test_selection": "BACKTEST_ONLY",
                "candidates": [],
            },
        }
        with patch.object(self.service, "start_experiment", return_value={"status": "RUNNING"}):
            self.service.repoint_and_rerun("exp_legacy", "new-branch", "new_commit")
        saved_spec = self.mock_repo.save_experiment.call_args[1]["spec"]
        assert saved_spec["test_selection"] == TestSelection.BOTH.value
        assert saved_spec["windows"] is not None

    def test_dispatch_both_pins_recorded_market_data_once(self) -> None:
        spec = ExperimentSpec(
            name="Shared Pin",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-branch-1",
            test_selection=TestSelection.BOTH,
            data_source=BacktestMarketDataSpec(
                source_type=BacktestDataSourceType.RECORDED_MARKET_DATA,
            ),
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                )
            ],
        )
        self.mock_bt_app.pin_market_data_snapshot.return_value = "snap_shared_123"
        mock_bt_session = MagicMock()
        mock_bt_session.id = "bt_1"
        self.mock_bt_app.start_backtest_run.return_value = mock_bt_session
        self.mock_wf_app.start_run.return_value = {"run_id": "wf_1"}

        self.service._dispatch_candidate_runs(spec, spec.candidates)

        self.mock_bt_app.pin_market_data_snapshot.assert_called_once()
        self.mock_wf_app.pin_market_data_snapshot.assert_not_called()
        bt_spec = self.mock_bt_app.start_backtest_run.call_args[0][0]
        wf_spec = self.mock_wf_app.start_run.call_args[0][0]
        assert bt_spec.data_source.dataset_id == "snap_shared_123"
        assert wf_spec.data_source.dataset_id == "snap_shared_123"

    def test_rerun_walk_forward_only_preserves_backtest_and_updates_windows(self) -> None:
        spec = ExperimentSpec(
            name="Rerun WF",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-branch-1",
            test_selection=TestSelection.BOTH,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                )
            ],
        )
        self.mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_rerun_1",
            "status": "COMPLETED",
            "spec": spec.model_dump(mode="json"),
            "run_bindings": [
                {
                    "candidate_id": "cand_current",
                    "backtest_session_id": "bt_existing_1",
                    "walk_forward_run_id": "wf_old_1",
                    "backtest_status": "COMPLETED",
                    "walk_forward_status": "COMPLETED",
                    "status": "COMPLETED",
                }
            ],
            "report": {},
            "run_history": [],
        }
        self.mock_wf_app.start_run.return_value = {"run_id": "wf_new_2"}

        overrides = StartExperimentRequest(
            test_selection=TestSelection.WALK_FORWARD_ONLY,
            windows=WalkForwardWindowSpec(
                window_mode=WindowMode.EXPANDING,
                train_candle_count=120,
                test_candle_count=40,
                step_size_candles=40,
                warmup_candle_count=20,
            ),
            execution=BacktestExecutionSpec(
                slippage_ticks=5,
                fee_rate=Decimal("0.002"),
            ),
        )

        with patch("threading.Thread"):
            self.service.start_experiment(
                "exp_rerun_1",
                TestSelection.WALK_FORWARD_ONLY,
                overrides,
            )

        self.mock_bt_app.start_backtest_run.assert_not_called()
        self.mock_wf_app.start_run.assert_called_once()

        saved_bindings = self.mock_repo.save_experiment.call_args[1]["run_bindings"]
        assert saved_bindings[0]["backtest_session_id"] == "bt_existing_1"
        assert saved_bindings[0]["backtest_status"] == "COMPLETED"
        assert saved_bindings[0]["walk_forward_run_id"] == "wf_new_2"
        assert saved_bindings[0]["walk_forward_status"] == "RUNNING"

        saved_spec = self.mock_repo.save_experiment.call_args[1]["spec"]
        assert saved_spec["test_selection"] == TestSelection.BOTH.value
        assert saved_spec["windows"]["window_mode"] == "expanding"
        assert saved_spec["windows"]["train_candle_count"] == 120
        assert saved_spec["execution"]["slippage_ticks"] == 5

    def test_staleness_detected_when_shared_config_changes_on_single_leg_rerun(self) -> None:
        old_cfg = {
            "data_source": {"source_type": "recorded_market_data", "dataset_id": "snap_1", "path": None},
            "period": None,
            "initial_balance": "10000.0",
            "execution": {"latency_ms": 500.0, "slippage_ticks": 2, "fee_rate": "0.001"},
        }
        new_cfg = {
            "data_source": {"source_type": "recorded_market_data", "dataset_id": "snap_2", "path": None},
            "period": None,
            "initial_balance": "25000.0",
            "execution": {"latency_ms": 500.0, "slippage_ticks": 5, "fee_rate": "0.001"},
        }
        stale_legs, stale_reasons = ExperimentApplicationService._compute_staleness(
            leg_configs={"backtest": old_cfg, "walk_forward": new_cfg},
            latest_config=new_cfg,
        )
        assert stale_legs == {"backtest": True, "walk_forward": False}
        assert set(stale_reasons["backtest"]) == {"initial_balance", "execution"}
        assert stale_reasons["walk_forward"] == []

    def test_partial_failure_preserves_backtest_when_walk_forward_fails(self) -> None:
        spec = ExperimentSpec(
            name="Partial Failure",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-branch-1",
            test_selection=TestSelection.BOTH,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                )
            ],
        )
        binding = {
            "candidate_id": "cand_current",
            "backtest_session_id": "bt_ok",
            "walk_forward_run_id": "wf_bad",
            "backtest_status": "RUNNING",
            "walk_forward_status": "RUNNING",
            "status": "RUNNING",
        }
        exp_record = {
            "experiment_id": "exp_partial",
            "status": "RUNNING",
            "spec": spec.model_dump(mode="json"),
            "run_bindings": [binding],
            "run_history": [],
        }

        mock_bt_repo = MagicMock()
        mock_wf_repo = MagicMock()
        mock_bt_session = MagicMock()
        mock_bt_session.status = "COMPLETED"
        mock_bt_repo.get_session.return_value = mock_bt_session
        mock_bt_repo.get_result_metrics.return_value = {
            "percentage_return": 7.5,
            "total_trades": 12,
        }
        mock_wf_repo.get_run.return_value = {
            "status": "FAILED",
            "error_message": "Not enough candles for requested folds",
        }

        def _get_repo(repo_cls):
            name = repo_cls.__name__
            if "Experiment" in name:
                return self.mock_repo
            if "Backtest" in name:
                return mock_bt_repo
            return mock_wf_repo

        self.mock_uow.get_repository.side_effect = _get_repo
        self.mock_repo.get_experiment.return_value = exp_record

        with patch("time.sleep"):
            self.service._watch_experiment_runs("exp_partial")

        assert binding["status"] == "PARTIAL"
        assert binding["backtest_status"] == "COMPLETED"
        assert binding["walk_forward_status"] == "FAILED"
        assert "Not enough candles" in binding["walk_forward_error"]

        self.mock_repo.update_report.assert_called_once()
        args, kwargs = self.mock_repo.update_report.call_args
        assert args[0] == "exp_partial"
        assert args[1] == ExperimentStatus.COMPLETED.value
        report = args[2]
        assert report["candidates"]["cand_current"]["backtest"]["percentage_return"] == 7.5
        assert report["candidates"]["cand_current"]["walk_forward"] is None
        assert "Not enough candles" in report["candidates"]["cand_current"]["walk_forward_error"]
        assert len(kwargs["run_history"]) == 1
        assert kwargs["run_history"][0]["run_number"] == 1

    def test_completion_handler_includes_walk_forward_metrics_when_present(self) -> None:
        report = {
            "candidates": {
                "cand_current": {
                    "name": "Current Config",
                    "backtest": {
                        "total_trades": 10,
                        "net_pnl": 50.0,
                        "win_rate_pct": 50.0,
                        "profit_factor": 1.2,
                        "max_drawdown": 15.0,
                    },
                    "walk_forward": {
                        "aggregate_oos_return_pct": 4.2,
                        "walk_forward_efficiency_ratio": 0.72,
                        "stability_classification": "ROBUST",
                    },
                },
                "cand_alt": {
                    "name": "Alt Mix",
                    "backtest": {
                        "total_trades": 14,
                        "net_pnl": 140.0,
                        "win_rate_pct": 64.0,
                        "profit_factor": 1.9,
                        "max_drawdown": 10.0,
                    },
                    "walk_forward": {
                        "aggregate_oos_return_pct": 9.8,
                        "walk_forward_efficiency_ratio": 0.85,
                        "stability_classification": "ROBUST",
                    },
                },
            }
        }
        outcomes = ExperimentCompletionAgentHandler._extract_outcomes(report)
        baseline = outcomes[0]
        best = ExperimentCompletionAgentHandler._select_best_candidate(outcomes)
        rec = ExperimentCompletionAgentHandler._build_recommendation(baseline, best)
        md = ExperimentCompletionAgentHandler._format_completed_markdown(
            title="Done",
            exp_name="Study",
            experiment_id="exp_1",
            outcomes=outcomes,
            recommendation=rec,
        )
        assert "+9.80%" in rec
        assert "ROBUST" in rec
        assert "validate with walk-forward testing" not in rec
        assert "| WF OOS | Stability |" in md
