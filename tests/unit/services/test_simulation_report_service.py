from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.dao.simulated_run_dao import SimulatedRunDao
from src.database.dao.simulation_report_dao import SimulationReportDao
from src.database.repositories.providers.postgres_promotion_repository import (
    PostgresSimulatedRunRepository,
)
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.server.services.promotion_policy import PromotionPolicy
from src.server.services.simulation_report_service import SimulationReportService


class DummyDbManager:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def get_unit_of_work(self):
        from src.database.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
        return SqlAlchemyUnitOfWork(self._session_factory())


class TestSimulationReportService:
    def setup_method(self):
        self.engine = create_engine("sqlite:///:memory:")
        SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(
            self.engine,
            tables=[SimulatedRunDao.__table__, SimulationReportDao.__table__],
        )
        self.session_factory = sessionmaker(bind=self.engine)
        self.db_manager = DummyDbManager(self.session_factory)

        # Seed run
        with self.db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run_repo.save_run(
                run_id="sim_run_test_01",
                experiment_id="exp_01",
                candidate_id="cand_01",
                candidate_commit="commit_123",
                config_hash="hash_abc",
                status="SIMULATING",
                market_data_spec={"ticker_symbol": "BTC_USD"},
                execution_spec={"initial_balance": 10000.0},
            )

        self.service = SimulationReportService(
            db_manager=self.db_manager,
            policy=PromotionPolicy(min_trades=5, max_drawdown_pct=15.0),
        )

    def teardown_method(self):
        self.engine.dispose()

    def test_calculate_metrics_with_trades_and_equity_curve(self):
        trades = [
            {"trade_id": "1", "pnl": 100.0, "strategy_name": "TrendBreakout"},
            {"trade_id": "2", "pnl": -50.0, "strategy_name": "TrendBreakout"},
            {"trade_id": "3", "pnl": 200.0, "strategy_name": "MeanReversion"},
            {"trade_id": "4", "pnl": -50.0, "strategy_name": "MeanReversion"},
            {"trade_id": "5", "pnl": 100.0, "strategy_name": "TrendBreakout"},
        ]
        equity_curve = [10000.0, 10100.0, 10050.0, 10250.0, 10200.0, 10300.0]

        summary = self.service._calculate_metrics(trades, equity_curve, runtime_errors=0)
        assert summary.executed_trades == 5
        assert summary.net_return_pct == 3.0
        assert summary.win_rate_pct == 60.0
        assert summary.profit_factor == 4.0
        assert summary.runtime_errors_count == 0

    def test_generate_and_save_report_success(self):
        trades = [
            {"trade_id": str(i), "pnl": 50.0, "strategy_name": "TrendBreakout"}
            for i in range(1, 7)
        ]
        equity_curve = [10000.0, 10050.0, 10100.0, 10150.0, 10200.0, 10250.0, 10300.0]

        report = self.service.generate_and_save_report(
            run_id="sim_run_test_01",
            trades=trades,
            equity_curve=equity_curve,
            operational_diagnostics={"missed_ticks": 0, "runtime_errors_count": 0},
        )

        assert report["decision"] == "PASS"
        assert report["summary_metrics"]["executed_trades"] == 6
        assert report["summary_metrics"]["net_return_pct"] == 3.0

        # Retrieve saved report
        saved = self.service.get_report_by_run("sim_run_test_01")
        assert saved is not None
        assert saved["report_id"] == report["report_id"]
        assert saved["decision"] == "PASS"
