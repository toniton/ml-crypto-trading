from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.interfaces.promotion import (
    GateDecision,
    PromoteToMainRequest,
    PromotionLifecycleState,
)
from src.database.dao.experiment_dao import ExperimentDao
from src.database.dao.promotion_audit_event_dao import PromotionAuditEventDao
from src.database.dao.promotion_record_dao import PromotionRecordDao
from src.database.dao.simulated_run_dao import SimulatedRunDao
from src.database.dao.simulation_report_dao import SimulationReportDao
from src.database.repositories.providers.postgres_experiment_repository import (
    PostgresExperimentRepository,
)
from src.database.repositories.providers.postgres_promotion_repository import (
    PostgresSimulatedRunRepository,
    PostgresSimulationReportRepository,
)
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.server.services.canonical_config import (
    build_canonical_effective_config,
    compute_canonical_config_hash,
    validate_commit_hash,
)
from src.server.services.main_promotion_service import MainPromotionService
from src.server.services.promotion_policy import PromotionPolicy
from src.server.services.simulation_orchestrator import SimulationOrchestrator
from src.server.services.simulation_report_service import SimulationReportService


class DummyDbManager:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def get_unit_of_work(self):
        from src.database.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
        return SqlAlchemyUnitOfWork(self._session_factory())


class TestPromotionHardening:
    def setup_method(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(
            self.engine,
            tables=[
                ExperimentDao.__table__,
                SimulatedRunDao.__table__,
                SimulationReportDao.__table__,
                PromotionRecordDao.__table__,
                PromotionAuditEventDao.__table__,
            ],
        )
        self.session_factory = sessionmaker(bind=self.engine)
        self.db_manager = DummyDbManager(self.session_factory)

        self.candidate = {
            "candidate_id": "cand_hardened",
            "name": "Hardened Candidate",
            "strategy_weights": {"TrendStrategy": 1.0},
            "candidate_commit_hash": "a1b2c3d4e5f6a1b2c3d4e5f6",
        }
        self.effective_config = build_canonical_effective_config(self.candidate, {})
        self.config_hash = compute_canonical_config_hash(self.effective_config)

        with self.db_manager.get_unit_of_work() as uow:
            exp_repo = uow.get_repository(PostgresExperimentRepository)
            exp_repo.save_experiment(
                experiment_id="exp_hardened",
                name="Hardened Exp",
                ticker_symbol="BTC_USD",
                branch_id="exp-branch-hardened",
                base_commit_hash="a1b2c3d4e5f6a1b2c3d4e5f6",
                status="DRAFT",
                spec={"candidates": [self.candidate]},
                run_bindings=[],
            )
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run_repo.save_run(
                run_id="run_hardened_01",
                experiment_id="exp_hardened",
                candidate_id="cand_hardened",
                candidate_commit="a1b2c3d4e5f6a1b2c3d4e5f6",
                config_hash=self.config_hash,
                status=PromotionLifecycleState.REPORT_READY.value,
                market_data_spec={},
                execution_spec={},
                effective_config=self.effective_config,
            )
            report_repo = uow.get_repository(PostgresSimulationReportRepository)
            report_repo.save_report(
                report_id="rep_hardened_01",
                run_id="run_hardened_01",
                config_hash=self.config_hash,
                decision=GateDecision.PASS.value,
                summary_metrics={"net_return_pct": 8.0, "executed_trades": 10},
                report_payload={},
            )

        self.mock_vcs = MagicMock()
        mock_preview = MagicMock()
        mock_preview.can_fast_forward = True
        mock_preview.conflicts = []
        mock_preview.merge_base_hash = "base_123"
        self.mock_vcs.preview_merge.return_value = mock_preview
        self.mock_vcs.checkout.return_value = {}

        mock_result = MagicMock()
        mock_result.merge_commit_hash = "merge_hash_final"
        self.mock_vcs.merge.return_value = mock_result

        self.policy = PromotionPolicy()
        self.promotion_service = MainPromotionService(
            db_manager=self.db_manager,
            vcs_service=self.mock_vcs,
            policy=self.policy,
        )

    def teardown_method(self):
        self.engine.dispose()

    def test_canonical_config_hash_covers_all_components(self):
        config_a = build_canonical_effective_config(
            {"candidate_id": "c1", "strategy_weights": {"A": 1.0}},
            {},
        )
        config_b = build_canonical_effective_config(
            {"candidate_id": "c1", "strategy_weights": {"A": 1.0}, "consensus": {"buy": 0.9}},
            {},
        )
        assert compute_canonical_config_hash(config_a) != compute_canonical_config_hash(config_b)

    def test_validate_commit_hash_rejects_head_and_short_strings(self):
        assert validate_commit_hash("HEAD") is False
        assert validate_commit_hash("head") is False
        assert validate_commit_hash("abc") is False
        assert validate_commit_hash("not_a_hex_commit_hash") is False
        assert validate_commit_hash("a1b2c3d4e5f6") is True

    def test_gate_c_cannot_be_bypassed_via_resolved_config(self):
        conflict_preview = MagicMock()
        conflict_preview.can_fast_forward = False
        conflict_preview.conflicts = [{"path": "strategies.json"}]
        self.mock_vcs.preview_merge.return_value = conflict_preview

        req = PromoteToMainRequest(
            idempotency_key="key_bypass_attempt",
            experiment_id="exp_hardened",
            candidate_id="cand_hardened",
            report_id="rep_hardened_01",
            run_id="run_hardened_01",
            approver="anonymous",
            resolved_config={"strategies": {}},
        )

        with pytest.raises(ValueError, match="not authorized to promote to main"):
            self.promotion_service.promote_to_main(req)

    def test_promotion_fails_if_report_config_hash_mismatches_candidate(self):
        with self.db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run_repo.save_run(
                run_id="run_mismatched_01",
                experiment_id="exp_hardened",
                candidate_id="cand_hardened",
                candidate_commit="a1b2c3d4e5f6a1b2c3d4e5f6",
                config_hash="stale_outdated_hash_999",
                status=PromotionLifecycleState.REPORT_READY.value,
                market_data_spec={},
                execution_spec={},
                effective_config={},
            )
            report_repo = uow.get_repository(PostgresSimulationReportRepository)
            report_repo.save_report(
                report_id="rep_mismatched_01",
                run_id="run_mismatched_01",
                config_hash="stale_outdated_hash_999",
                decision=GateDecision.PASS.value,
                summary_metrics={"net_return_pct": 9.0},
                report_payload={},
            )

        req = PromoteToMainRequest(
            idempotency_key="key_hash_mismatch",
            experiment_id="exp_hardened",
            candidate_id="cand_hardened",
            report_id="rep_mismatched_01",
            run_id="run_mismatched_01",
            approver="alice@rio.trade",
        )

        with pytest.raises(ValueError, match="Candidate configuration hash mismatch"):
            self.promotion_service.promote_to_main(req)

    def test_startup_recovery_transitions_interrupted_runs_to_failed(self):
        with self.db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run_repo.save_run(
                run_id="run_orphaned_01",
                experiment_id="exp_hardened",
                candidate_id="cand_hardened",
                candidate_commit="a1b2c3d4e5f6a1b2c3d4e5f6",
                config_hash="some_hash",
                status=PromotionLifecycleState.SIMULATING.value,
                market_data_spec={},
                execution_spec={},
            )

        report_service = SimulationReportService(self.db_manager, self.policy)
        orchestrator = SimulationOrchestrator(
            db_manager=self.db_manager,
            report_service=report_service,
            policy=self.policy,
        )

        recovered = orchestrator.recover_interrupted_runs()
        assert recovered >= 1

        run = orchestrator.get_simulated_run("run_orphaned_01")
        assert run is not None
        assert run["status"] == PromotionLifecycleState.FAILED.value
        assert "interrupted" in run["error_message"].lower()
