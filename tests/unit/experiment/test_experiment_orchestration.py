from __future__ import annotations

from unittest.mock import MagicMock, patch

from api.interfaces.experiment import (
    CandidateType,
    ExperimentCandidate,
    ExperimentSpec,
    ExperimentStatus,
    TestSelection,
)
from src.server.services.experiment_application_service import (
    ExperimentApplicationService,
)


class TestExperimentOrchestration:  # pylint: disable=attribute-defined-outside-init,protected-access
    def setup_method(self):
        self.mock_db = MagicMock()
        self.mock_uow = MagicMock()
        self.mock_db.get_unit_of_work.return_value.__enter__.return_value = self.mock_uow
        self.mock_repo = MagicMock()
        self.mock_uow.get_repository.return_value = self.mock_repo

        self.mock_vcs = MagicMock()
        self.mock_vcs.resolve_commit_hash.return_value = "commit_sha_base_001"

        self.mock_backtest_service = MagicMock()
        self.mock_bt_app = MagicMock()
        self.mock_wf_app = MagicMock()

        self.service = ExperimentApplicationService(
            db_manager=self.mock_db,
            vcs_service=self.mock_vcs,
            backtest_service=self.mock_backtest_service,
            backtest_app_service=self.mock_bt_app,
            walk_forward_app_service=self.mock_wf_app,
        )

    def test_start_experiment_dispatches_backtest_only(self):
        spec = ExperimentSpec(
            name="BTC Backtest Only",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-btc-branch",
            test_selection=TestSelection.BACKTEST_ONLY,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current Configuration",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                )
            ],
        )
        self.mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_bt_01",
            "status": "DRAFT",
            "spec": spec.model_dump(mode="json"),
            "run_bindings": [],
        }

        mock_bt_session = MagicMock()
        mock_bt_session.id = "bt_sess_101"
        self.mock_bt_app.start_backtest_run.return_value = mock_bt_session

        with patch("threading.Thread") as mock_thread:
            self.service.start_experiment("exp_bt_01")
            mock_thread.assert_called_once()

        self.mock_bt_app.start_backtest_run.assert_called_once()
        self.mock_wf_app.start_run.assert_not_called()

        saved_bindings = self.mock_repo.save_experiment.call_args[1]["run_bindings"]
        assert len(saved_bindings) == 1
        assert saved_bindings[0]["backtest_session_id"] == "bt_sess_101"
        assert saved_bindings[0]["walk_forward_run_id"] is None
        assert saved_bindings[0]["status"] == "RUNNING"

    def test_start_experiment_dispatches_walk_forward_only(self):
        spec = ExperimentSpec(
            name="BTC Walk Forward Only",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-btc-branch",
            test_selection=TestSelection.WALK_FORWARD_ONLY,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current Configuration",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                )
            ],
        )
        self.mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_wf_01",
            "status": "DRAFT",
            "spec": spec.model_dump(mode="json"),
            "run_bindings": [],
        }

        self.mock_wf_app.start_run.return_value = {"run_id": "wf_run_202"}

        with patch("threading.Thread"):
            self.service.start_experiment("exp_wf_01")

        self.mock_bt_app.start_backtest_run.assert_not_called()
        self.mock_wf_app.start_run.assert_called_once()

        saved_bindings = self.mock_repo.save_experiment.call_args[1]["run_bindings"]
        assert len(saved_bindings) == 1
        assert saved_bindings[0]["backtest_session_id"] is None
        assert saved_bindings[0]["walk_forward_run_id"] == "wf_run_202"
        assert saved_bindings[0]["status"] == "RUNNING"

    def test_start_experiment_dispatches_both(self):
        spec = ExperimentSpec(
            name="BTC Dual Mode",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-btc-branch",
            test_selection=TestSelection.BOTH,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current Configuration",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                ),
                ExperimentCandidate(
                    candidate_id="cand_weights",
                    name="Proposed Weights",
                    candidate_type=CandidateType.PROPOSED_WEIGHTS,
                    strategy_weights={"TrendFollower": 1.5},
                ),
            ],
        )
        self.mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_both_01",
            "status": "DRAFT",
            "spec": spec.model_dump(mode="json"),
            "run_bindings": [],
        }

        mock_bt_session = MagicMock()
        mock_bt_session.id = "bt_sess_303"
        self.mock_bt_app.start_backtest_run.return_value = mock_bt_session
        self.mock_wf_app.start_run.return_value = {"run_id": "wf_run_404"}

        with patch("threading.Thread"):
            self.service.start_experiment("exp_both_01")

        assert self.mock_bt_app.start_backtest_run.call_count == 2
        assert self.mock_wf_app.start_run.call_count == 2

        saved_bindings = self.mock_repo.save_experiment.call_args[1]["run_bindings"]
        assert len(saved_bindings) == 2
        assert saved_bindings[0]["backtest_session_id"] == "bt_sess_303"
        assert saved_bindings[0]["walk_forward_run_id"] == "wf_run_404"

    def test_cancel_experiment(self):
        self.mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_cancel_01",
            "status": "RUNNING",
            "run_bindings": [
                {"candidate_id": "c1", "status": "RUNNING"},
                {"candidate_id": "c2", "status": "COMPLETED"},
            ],
        }

        success = self.service.cancel_experiment("exp_cancel_01")
        assert success is True
        self.mock_repo.update_status.assert_called_once_with("exp_cancel_01", ExperimentStatus.CANCELLED.value)

        updated_bindings = self.mock_repo.update_bindings.call_args[0][1]
        assert updated_bindings[0]["status"] == "CANCELLED"
        assert updated_bindings[1]["status"] == "COMPLETED"

    def test_retry_candidate(self):
        spec = ExperimentSpec(
            name="Retry Test",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-btc-branch",
            test_selection=TestSelection.BACKTEST_ONLY,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_failed",
                    name="Failed Candidate",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                )
            ],
        )
        self.mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_retry_01",
            "status": "RUNNING",
            "spec": spec.model_dump(mode="json"),
            "run_bindings": [
                {
                    "candidate_id": "cand_failed",
                    "backtest_session_id": "old_bt_1",
                    "status": "FAILED",
                    "error": "Timeout error",
                }
            ],
        }

        mock_new_session = MagicMock()
        mock_new_session.id = "bt_retry_session_999"
        self.mock_bt_app.start_backtest_run.return_value = mock_new_session

        with patch("threading.Thread"):
            self.service.retry_candidate("exp_retry_01", "cand_failed")

        updated_bindings = self.mock_repo.update_bindings.call_args[0][1]
        assert len(updated_bindings) == 1
        assert updated_bindings[0]["candidate_id"] == "cand_failed"
        assert updated_bindings[0]["backtest_session_id"] == "bt_retry_session_999"
        assert updated_bindings[0]["status"] == "RUNNING"

    def test_compute_experiment_report_deltas(self):
        spec = ExperimentSpec(
            name="Report Aggregation Test",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-btc-branch",
            test_selection=TestSelection.BOTH,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current Config",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                ),
                ExperimentCandidate(
                    candidate_id="cand_custom",
                    name="Custom Weights",
                    candidate_type=CandidateType.PROPOSED_WEIGHTS,
                ),
            ],
        )
        bindings = [
            {
                "candidate_id": "cand_current",
                "backtest_session_id": "bt_1",
                "walk_forward_run_id": "wf_1",
                "status": "COMPLETED",
            },
            {
                "candidate_id": "cand_custom",
                "backtest_session_id": "bt_2",
                "walk_forward_run_id": "wf_2",
                "status": "COMPLETED",
            },
        ]

        mock_uow = MagicMock()
        mock_bt_repo = MagicMock()
        mock_wf_repo = MagicMock()

        def _get_repo(repo_type):
            name = repo_type.__name__
            if "Backtest" in name:
                return mock_bt_repo
            return mock_wf_repo

        mock_uow.get_repository.side_effect = _get_repo

        mock_bt_repo.get_result_metrics.side_effect = lambda sid: (
            {"percentage_return": 10.0, "max_drawdown_pct": 5.0}
            if sid == "bt_1"
            else {"percentage_return": 15.0, "max_drawdown_pct": 4.0}
        )
        mock_wf_repo.get_run.side_effect = lambda rid: (
            {"summary": {"aggregate_oos_return_pct": 8.0, "verdict": "ROBUST"}}
            if rid == "wf_1"
            else {"summary": {"aggregate_oos_return_pct": 14.0, "verdict": "ROBUST"}}
        )

        report = ExperimentApplicationService._compute_experiment_report(mock_uow, spec, bindings)

        assert report["summary"]["total_candidates"] == 2
        assert report["summary"]["completed_candidates"] == 2
        assert report["summary"]["failed_candidates"] == 0

        current_entry = report["candidates"]["cand_current"]
        custom_entry = report["candidates"]["cand_custom"]

        assert current_entry["backtest"]["percentage_return"] == 10.0
        assert custom_entry["backtest"]["percentage_return"] == 15.0
        # Delta: 15.0 - 10.0 = 5.0
        assert custom_entry["deltas"]["backtest_return_diff"] == 5.0
        # Walk forward delta: 14.0 - 8.0 = 6.0
        assert custom_entry["deltas"]["walk_forward_oos_return_diff"] == 6.0
