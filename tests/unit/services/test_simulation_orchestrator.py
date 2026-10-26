from __future__ import annotations

import time
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.interfaces.promotion import CreateSimulatedRunRequest, SimulatedRunMarketDataSpec
from src.database.dao.experiment_dao import ExperimentDao
from src.database.dao.promotion_audit_event_dao import PromotionAuditEventDao
from src.database.dao.simulated_run_dao import SimulatedRunDao
from src.database.dao.simulation_report_dao import SimulationReportDao
from src.database.repositories.providers.postgres_experiment_repository import (
    PostgresExperimentRepository,
)
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.server.services.promotion_policy import PromotionPolicy
from src.server.services.simulation_orchestrator import SimulationOrchestrator
from src.server.services.simulation_report_service import SimulationReportService


class DummyDbManager:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def get_unit_of_work(self):
        from src.database.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
        return SqlAlchemyUnitOfWork(self._session_factory())


class TestSimulationOrchestrator:
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
                PromotionAuditEventDao.__table__,
            ],
        )
        self.session_factory = sessionmaker(bind=self.engine)
        self.db_manager = DummyDbManager(self.session_factory)

        # Seed valid experiment with a candidate
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
                    "candidates": [
                        {
                            "candidate_id": "cand_trend",
                            "name": "Trend Candidate",
                            "strategy_weights": {"TrendBreakout": 1.5},
                            "candidate_commit_hash": "commit_head_123",
                        },
                        {
                            "candidate_id": "cand_invalid",
                            "name": "Invalid Candidate",
                            "strategy_weights": {},
                        },
                    ]
                },
                run_bindings=[{"run_id": "prior_bt_1"}],
            )

        self.policy = PromotionPolicy(min_trades=5)
        self.report_service = SimulationReportService(self.db_manager, self.policy)
        self.orchestrator = SimulationOrchestrator(
            db_manager=self.db_manager,
            report_service=self.report_service,
            policy=self.policy,
        )

    def teardown_method(self):
        for run_id in list(self.orchestrator._cancellation_events.keys()):
            self.orchestrator.cancel_simulated_run(run_id)
        for thread in list(self.orchestrator._active_threads.values()):
            thread.join(timeout=1.0)
        self.engine.dispose()

    def test_start_simulated_run_enforces_gate_a(self):
        # Candidate with empty weights fails Gate A
        req = CreateSimulatedRunRequest(
            experiment_id="exp_btc",
            candidate_id="cand_invalid",
        )
        with pytest.raises(ValueError, match="Gate A failed"):
            self.orchestrator.start_simulated_run(req)

    def test_start_simulated_run_executes_and_reaches_report_ready(self):
        req = CreateSimulatedRunRequest(
            experiment_id="exp_btc",
            candidate_id="cand_trend",
            market_data=SimulatedRunMarketDataSpec(ticker_symbol="BTC_USD", duration_hours=3, real_time=False),
        )

        res = self.orchestrator.start_simulated_run(req)
        assert res["run_id"].startswith("sim_run_")
        assert res["status"] == "SIMULATION_QUEUED"

        run_id = res["run_id"]
        for _ in range(30):
            time.sleep(0.1)
            run = self.orchestrator.get_simulated_run(run_id)
            if run and run["status"] == "REPORT_READY":
                break

        final_run = self.orchestrator.get_simulated_run(run_id)
        assert final_run is not None
        assert final_run["status"] == "REPORT_READY"

        report = self.report_service.get_report_by_run(run_id)
        assert report is not None
        assert report["decision"] == "PASS"
        assert report["summary_metrics"]["executed_trades"] >= 5

    def test_real_time_simulated_run_observes_and_can_be_concluded(self):
        req = CreateSimulatedRunRequest(
            experiment_id="exp_btc",
            candidate_id="cand_trend",
            market_data=SimulatedRunMarketDataSpec(ticker_symbol="BTC_USD", duration_hours=48, real_time=True),
        )

        res = self.orchestrator.start_simulated_run(req)
        run_id = res["run_id"]

        time.sleep(0.2)
        simulating_run = self.orchestrator.get_simulated_run(run_id)
        assert simulating_run is not None
        assert simulating_run["status"] == "SIMULATING"
        assert "planned_end_at" in simulating_run["market_data_spec"]

        conclude_res = self.orchestrator.conclude_simulated_run(run_id)
        assert conclude_res["status"] == "REPORT_READY"

        final_run = self.orchestrator.get_simulated_run(run_id)
        assert final_run is not None
        assert final_run["status"] == "REPORT_READY"

        report = self.report_service.get_report_by_run(run_id)
        assert report is not None
        assert report["decision"] == "PASS"

    def test_cancel_simulated_run(self):
        req = CreateSimulatedRunRequest(
            experiment_id="exp_btc",
            candidate_id="cand_trend",
        )
        res = self.orchestrator.start_simulated_run(req)
        run_id = res["run_id"]

        cancel_res = self.orchestrator.cancel_simulated_run(run_id)
        assert cancel_res["status"] == "CANCELLED"

        run = self.orchestrator.get_simulated_run(run_id)
        assert run["status"] == "CANCELLED"
