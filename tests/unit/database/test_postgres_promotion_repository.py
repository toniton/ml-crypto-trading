from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.dao.promotion_audit_event_dao import PromotionAuditEventDao
from src.database.dao.promotion_record_dao import PromotionRecordDao
from src.database.dao.simulated_run_dao import SimulatedRunDao
from src.database.dao.simulation_report_dao import SimulationReportDao
from src.database.repositories.providers.postgres_promotion_repository import (
    PostgresPromotionAuditRepository,
    PostgresPromotionRecordRepository,
    PostgresSimulatedRunRepository,
    PostgresSimulationReportRepository,
)
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


class TestPromotionPipelinePersistence:  # pylint: disable=attribute-defined-outside-init
    def setup_method(self):
        self.engine = create_engine("sqlite:///:memory:")
        SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(
            self.engine,
            tables=[
                SimulatedRunDao.__table__,
                SimulationReportDao.__table__,
                PromotionRecordDao.__table__,
                PromotionAuditEventDao.__table__,
            ],
        )
        session_factory = sessionmaker(bind=self.engine)
        self.session = session_factory()
        self.run_repo = PostgresSimulatedRunRepository(database_session=self.session)
        self.report_repo = PostgresSimulationReportRepository(database_session=self.session)
        self.promotion_repo = PostgresPromotionRecordRepository(database_session=self.session)
        self.audit_repo = PostgresPromotionAuditRepository(database_session=self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_save_and_get_simulated_run(self):
        self.run_repo.save_run(
            run_id="run_001",
            experiment_id="exp_123",
            candidate_id="cand_1",
            candidate_commit="commit_aaa",
            config_hash="hash_111",
            status="SIMULATION_QUEUED",
            market_data_spec={"ticker_symbol": "BTC_USD", "duration_hours": 24},
            execution_spec={"initial_balance": 10000.0, "slippage_ticks": 1},
        )
        self.session.commit()

        run = self.run_repo.get_run("run_001")
        assert run is not None
        assert run["run_id"] == "run_001"
        assert run["experiment_id"] == "exp_123"
        assert run["status"] == "SIMULATION_QUEUED"
        assert run["market_data_spec"]["ticker_symbol"] == "BTC_USD"

    def test_update_simulated_run_status(self):
        self.run_repo.save_run(
            run_id="run_002",
            experiment_id="exp_123",
            candidate_id="cand_1",
            candidate_commit="commit_aaa",
            config_hash="hash_111",
            status="SIMULATING",
            market_data_spec={"ticker_symbol": "ETH_USD"},
            execution_spec={},
        )
        self.session.commit()

        self.run_repo.update_status("run_002", "REPORT_READY")
        self.session.commit()

        updated = self.run_repo.get_run("run_002")
        assert updated is not None
        assert updated["status"] == "REPORT_READY"

    def test_save_and_get_simulation_report(self):
        self.report_repo.save_report(
            report_id="rep_001",
            run_id="run_001",
            config_hash="hash_111",
            decision="PASS",
            summary_metrics={
                "net_return_pct": 5.2,
                "max_drawdown_pct": 3.1,
                "executed_trades": 12,
                "win_rate_pct": 66.7,
                "profit_factor": 1.85,
                "baseline_return_diff_pct": 2.1,
                "runtime_errors_count": 0,
            },
            report_payload={"sections": ["identity", "performance", "decision"]},
        )
        self.session.commit()

        report = self.report_repo.get_report_by_run("run_001")
        assert report is not None
        assert report["decision"] == "PASS"
        assert report["summary_metrics"]["executed_trades"] == 12

    def test_promotion_record_idempotency(self):
        self.promotion_repo.save_promotion(
            promotion_id="promo_001",
            idempotency_key="idem_key_abc",
            experiment_id="exp_123",
            candidate_id="cand_1",
            source_commit="commit_aaa",
            target_ref="refs/heads/main",
            status="PROMOTED",
            approver="alice@rio.trade",
            gate_results={"gate_a": "PASS", "gate_b": "PASS", "gate_c": "PASS"},
            approval_notes="Approved after 48h forward paper trading.",
            merge_commit_hash="merge_commit_zzz",
        )
        self.session.commit()

        existing = self.promotion_repo.get_by_idempotency_key("idem_key_abc")
        assert existing is not None
        assert existing["promotion_id"] == "promo_001"
        assert existing["merge_commit_hash"] == "merge_commit_zzz"

        # Re-save with same idempotency key updates existing rather than creating duplicate
        self.promotion_repo.save_promotion(
            promotion_id="promo_002",
            idempotency_key="idem_key_abc",
            experiment_id="exp_123",
            candidate_id="cand_1",
            source_commit="commit_aaa",
            target_ref="refs/heads/main",
            status="PROMOTED",
            approver="alice@rio.trade",
            gate_results={"gate_a": "PASS", "gate_b": "PASS", "gate_c": "PASS"},
            approval_notes="Updated notes",
        )
        self.session.commit()

        promotions = self.promotion_repo.list_promotions(experiment_id="exp_123")
        assert len(promotions) == 1
        assert promotions[0]["approval_notes"] == "Updated notes"

    def test_promotion_audit_event_logging(self):
        self.audit_repo.record_event(
            event_id="evt_001",
            event_type="GATE_C_APPROVAL",
            from_state="PROMOTION_ELIGIBLE",
            to_state="PROMOTED",
            actor="operator_1",
            payload={"commit": "merge_commit_zzz"},
            promotion_id="promo_001",
        )
        self.session.commit()

        events = self.audit_repo.list_events(promotion_id="promo_001")
        assert len(events) == 1
        assert events[0]["event_type"] == "GATE_C_APPROVAL"
        assert events[0]["from_state"] == "PROMOTION_ELIGIBLE"
        assert events[0]["to_state"] == "PROMOTED"
        assert events[0]["actor"] == "operator_1"
