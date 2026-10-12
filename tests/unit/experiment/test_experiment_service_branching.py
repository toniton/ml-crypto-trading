from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.interfaces.experiment import (
    CandidateType,
    ControlPolicySpec,
    CreateExperimentRequest,
    ExperimentSpec,
    ExperimentStatus,
    TestSelection,
)
from src.server.services.experiment_application_service import (
    ExperimentApplicationService,
)


class TestExperimentServiceBranching:
    def test_create_experiment_resolves_head_and_forks_branch(self):
        mock_db = MagicMock()
        mock_uow = MagicMock()
        mock_db.get_unit_of_work.return_value.__enter__.return_value = mock_uow
        mock_repo = MagicMock()
        mock_uow.get_repository.return_value = mock_repo

        mock_vcs = MagicMock()
        mock_vcs.resolve_commit_hash.return_value = "commit_sha_head_12345"

        mock_backtest = MagicMock()
        mock_backtest.create_branch.return_value = {
            "branch_id": "exp-momentum-test-4321",
            "ref_name": "refs/heads/backtest/exp-momentum-test-4321",
            "source_commit_hash": "commit_sha_head_12345",
        }

        service = ExperimentApplicationService(
            db_manager=mock_db,
            vcs_service=mock_vcs,
            backtest_service=mock_backtest,
        )

        req = CreateExperimentRequest(
            name="Momentum Test",
            ticker_symbol="BTC_USD",
            test_selection=TestSelection.BOTH,
            control_policy=ControlPolicySpec(enable_equal_weight_baseline=True),
        )

        result = service.create_experiment(req)

        assert result["name"] == "Momentum Test"
        assert result["ticker_symbol"] == "BTC_USD"
        assert result["base_commit_hash"] == "commit_sha_head_12345"
        assert result["branch_id"] == "exp-momentum-test-4321"
        assert result["status"] == ExperimentStatus.DRAFT.value

        # Verify candidate arms pre-populated
        spec = result["spec"]
        candidates = spec["candidates"]
        assert len(candidates) == 2
        assert candidates[0]["candidate_id"] == "cand_current"
        assert candidates[0]["candidate_type"] == CandidateType.CURRENT_CONFIG.value
        assert candidates[1]["candidate_id"] == "cand_equal_weight"
        assert candidates[1]["candidate_type"] == CandidateType.EQUAL_WEIGHT.value

        mock_backtest.create_branch.assert_called_once_with(
            name="exp-Momentum Test",
            description="Experiment branch for Momentum Test",
            source_commit_hash="commit_sha_head_12345",
            author="experiment-service",
        )
        mock_repo.save_experiment.assert_called_once()

    def test_delete_experiment_removes_branch_and_record(self):
        mock_db = MagicMock()
        mock_uow = MagicMock()
        mock_db.get_unit_of_work.return_value.__enter__.return_value = mock_uow
        mock_repo = MagicMock()
        mock_uow.get_repository.return_value = mock_repo

        mock_vcs = MagicMock()
        mock_backtest = MagicMock()

        mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_del_123",
            "branch_id": "exp-del-branch",
        }
        mock_repo.delete_experiment.return_value = True

        service = ExperimentApplicationService(
            db_manager=mock_db,
            vcs_service=mock_vcs,
            backtest_service=mock_backtest,
        )

        success = service.delete_experiment("exp_del_123")
        assert success is True
        mock_backtest.delete_branch.assert_called_once_with("exp-del-branch")
        mock_repo.delete_experiment.assert_called_once_with("exp_del_123")

    def test_update_spec_blocks_non_draft(self):
        mock_db = MagicMock()
        mock_uow = MagicMock()
        mock_db.get_unit_of_work.return_value.__enter__.return_value = mock_uow
        mock_repo = MagicMock()
        mock_uow.get_repository.return_value = mock_repo

        mock_vcs = MagicMock()
        mock_backtest = MagicMock()

        mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_running_123",
            "status": ExperimentStatus.RUNNING.value,
        }

        service = ExperimentApplicationService(
            db_manager=mock_db,
            vcs_service=mock_vcs,
            backtest_service=mock_backtest,
        )

        new_spec = ExperimentSpec(
            name="Updated Name",
            ticker_symbol="BTC_USD",
            base_commit_hash="abc",
            branch_id="b1",
        )

        with pytest.raises(ValueError, match="Cannot update experiment.*RUNNING"):
            service.update_experiment_spec("exp_running_123", new_spec)
