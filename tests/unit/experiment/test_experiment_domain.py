from __future__ import annotations

from decimal import Decimal

from api.interfaces.experiment import (
    CandidateType,
    CreateExperimentRequest,
    ExperimentCandidate,
    ExperimentRecord,
    ExperimentSpec,
    ExperimentStatus,
    TestSelection,
)


class TestExperimentDomain:
    def test_create_experiment_request_defaults(self):
        req = CreateExperimentRequest(
            name="BTC Momentum Comparison",
            ticker_symbol="BTC_USD",
        )
        assert req.name == "BTC Momentum Comparison"
        assert req.ticker_symbol == "BTC_USD"
        assert req.test_selection == TestSelection.BOTH
        assert req.initial_balance == Decimal("10000.0")
        assert req.control_policy.enable_equal_weight_baseline is True  # pylint: disable=no-member
        assert req.control_policy.random_seeds == [42]  # pylint: disable=no-member
        assert req.source_commit_hash is None

    def test_candidate_types_and_defaults(self):
        cand = ExperimentCandidate(
            candidate_id="cand_1",
            name="Proposed Trend Weights",
            candidate_type=CandidateType.PROPOSED_WEIGHTS,
            strategy_weights={"TrendFollower": 1.5, "MeanReversion": 0.5},
        )
        assert cand.candidate_id == "cand_1"
        assert cand.candidate_type == CandidateType.PROPOSED_WEIGHTS
        assert cand.strategy_weights["TrendFollower"] == 1.5

    def test_experiment_spec_serialization(self):
        spec = ExperimentSpec(
            name="ETH Volatility Experiment",
            ticker_symbol="ETH_USD",
            base_commit_hash="abc1234567890",
            branch_id="exp-eth-vol-1234",
            test_selection=TestSelection.WALK_FORWARD_ONLY,
            initial_balance=Decimal("25000.0"),
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_cur",
                    name="Current",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                )
            ],
        )
        dumped = spec.model_dump(mode="json")
        assert dumped["name"] == "ETH Volatility Experiment"
        assert dumped["test_selection"] == "WALK_FORWARD_ONLY"
        assert dumped["initial_balance"] == "25000.0"
        assert len(dumped["candidates"]) == 1

    def test_experiment_record_creation(self):
        spec = ExperimentSpec(
            name="Test Experiment",
            ticker_symbol="BTC_USD",
            base_commit_hash="deadbeef",
            branch_id="exp-bt-123",
        )
        record = ExperimentRecord(
            experiment_id="exp_001",
            name="Test Experiment",
            ticker_symbol="BTC_USD",
            branch_id="exp-bt-123",
            base_commit_hash="deadbeef",
            status=ExperimentStatus.DRAFT,
            spec=spec,
        )
        assert record.status == ExperimentStatus.DRAFT
        assert record.run_bindings == []
        assert record.report is None
