from __future__ import annotations

from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.interfaces.promotion import GateDecision, PromoteToMainRequest, PromotionLifecycleState
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
from src.server.routes.promotion_routes import create_promotion_router
from src.server.services.canonical_config import CanonicalConfigService
from src.server.services.main_promotion_service import MainPromotionService
from src.server.services.promotion_policy import PromotionPolicy


class DummyDbManager:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def get_unit_of_work(self):
        from src.database.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
        return SqlAlchemyUnitOfWork(self._session_factory())


class TestMainPromotionService:
    def setup_method(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
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

        self.candidate_config = {
            "candidate_id": "cand_trend",
            "name": "Trend Candidate",
            "strategy_weights": {"TrendBreakout": 1.5},
            "candidate_commit_hash": "commit_head_123",
        }
        self.effective_config = CanonicalConfigService.build_effective_config(self.candidate_config, {})
        self.config_hash = CanonicalConfigService.compute_hash(self.effective_config)

        # Seed experiment
        with self.db_manager.get_unit_of_work() as uow:
            exp_repo = uow.get_repository(PostgresExperimentRepository)
            exp_repo.save_experiment(
                experiment_id="exp_btc",
                name="BTC Strategy Experiment",
                ticker_symbol="BTC_USD",
                branch_id="exp-branch-01",
                base_commit_hash="commit_head_123",
                status="DRAFT",
                spec={
                    "candidates": [self.candidate_config]
                },
                run_bindings=[],
            )

            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run_repo.save_run(
                run_id="run_pass_01",
                experiment_id="exp_btc",
                candidate_id="cand_trend",
                candidate_commit="commit_head_123",
                config_hash=self.config_hash,
                status=PromotionLifecycleState.REPORT_READY.value,
                market_data_spec={},
                execution_spec={},
                effective_config=self.effective_config,
            )

            report_repo = uow.get_repository(PostgresSimulationReportRepository)
            report_repo.save_report(
                report_id="rep_pass_01",
                run_id="run_pass_01",
                config_hash=self.config_hash,
                decision=GateDecision.PASS.value,
                summary_metrics={"net_return_pct": 5.0, "executed_trades": 8},
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
        mock_result.merge_commit_hash = "merge_commit_999"
        self.mock_vcs.merge.return_value = mock_result

        self.service = MainPromotionService(
            db_manager=self.db_manager,
            vcs_service=self.mock_vcs,
            policy=PromotionPolicy(),
        )

    def teardown_method(self):
        self.engine.dispose()

    def test_preview_promotion_success(self):
        req = PromoteToMainRequest(
            idempotency_key="key_001",
            experiment_id="exp_btc",
            candidate_id="cand_trend",
            report_id="rep_pass_01",
            run_id="run_pass_01",
            approver="alice@rio.trade",
        )

        preview = self.service.preview_promotion(req)
        assert preview["eligible"] is True
        assert preview["gate_c"]["decision"] == "PASS"
        assert preview["source_commit"] == "commit_head_123"

    def test_promote_to_main_executes_merge_and_records_audit(self):
        req = PromoteToMainRequest(
            idempotency_key="key_002",
            experiment_id="exp_btc",
            candidate_id="cand_trend",
            report_id="rep_pass_01",
            run_id="run_pass_01",
            approver="alice@rio.trade",
            approval_notes="Reviewed paper trading report.",
        )

        result = self.service.promote_to_main(req)
        assert result["status"] == "PROMOTED"
        assert result["merge_commit_hash"] == "merge_commit_999"
        assert result["live_trading_status"] == "UNTOUCHED_SAFEGUARDED"

        self.mock_vcs.merge.assert_called_once()

    def test_promote_to_main_is_idempotent(self):
        req = PromoteToMainRequest(
            idempotency_key="key_idempotent_01",
            experiment_id="exp_btc",
            candidate_id="cand_trend",
            report_id="rep_pass_01",
            run_id="run_pass_01",
            approver="alice@rio.trade",
        )

        first_res = self.service.promote_to_main(req)
        assert first_res["status"] == "PROMOTED"
        call_count_before = self.mock_vcs.merge.call_count

        # Second invocation with same idempotency key must not call VCS merge again
        second_res = self.service.promote_to_main(req)
        assert second_res["promotion_id"] == first_res["promotion_id"]
        assert self.mock_vcs.merge.call_count == call_count_before

    def test_promote_to_main_blocked_if_no_passing_simulation(self):
        req = PromoteToMainRequest(
            idempotency_key="key_003",
            experiment_id="exp_btc",
            candidate_id="cand_nonexistent",
            report_id="rep_missing",
            run_id="run_missing",
            approver="alice@rio.trade",
        )

        with pytest.raises(ValueError, match="not found"):
            self.service.promote_to_main(req)

    def test_promotion_audit_endpoint_returns_recorded_events(self):
        req = PromoteToMainRequest(
            idempotency_key="key_audit_01",
            experiment_id="exp_btc",
            candidate_id="cand_trend",
            report_id="rep_pass_01",
            run_id="run_pass_01",
            approver="alice@rio.trade",
        )
        promoted = self.service.promote_to_main(req)

        app = FastAPI()
        app.state.main_promotion_service = self.service
        app.include_router(create_promotion_router())
        client = TestClient(app)

        res = client.get(
            "/api/v1/promotions/audit",
            params={"promotion_id": promoted["promotion_id"]},
        )

        assert res.json()[0]["event_type"] == "PROMOTED_TO_MAIN"
