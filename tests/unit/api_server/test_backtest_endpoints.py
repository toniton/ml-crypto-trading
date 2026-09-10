import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
    ExecutionConfiguration,
)
from src.agent import AgentGateway
from src.backtest.domain.result import BacktestResult
from src.backtest.domain.session import BacktestSession, BacktestSessionStatus
from src.database.repositories.providers.postgres_backtest_repository import PostgresBacktestRepository
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.events.message_event_bus import MessageEventBus
from src.server.app import ChatApp
from src.vcs.application.service import VCSService
from tests.unit.agent.fakes import FakeLlmAdapter


def build_app(db_manager):
    return ChatApp.create(
        agent=AgentGateway(FakeLlmAdapter(chunks=["ok"]), vcs=MagicMock(spec=VCSService)),
        event_bus=MessageEventBus(),
        db_manager=db_manager,
    )


class TestBacktestEndpoints(unittest.TestCase):
    def _setup_db_manager(self):
        db_manager = MagicMock(spec=SqlAlchemyDatabaseManager)
        uow = MagicMock()
        repo = MagicMock(spec=PostgresBacktestRepository)
        db_manager.get_unit_of_work.return_value.__enter__.return_value = uow

        def get_repo(repo_cls):
            if repo_cls == PostgresBacktestRepository:
                return repo
            return MagicMock()

        uow.get_repository.side_effect = get_repo
        return db_manager, repo

    def test_list_backtests_endpoint(self):
        db_manager, repo = self._setup_db_manager()

        request = BacktestRequest(
            ticker_symbol="BTC_USD",
            initial_balance=Decimal("10000.0"),
            data_source=BacktestDataSourceRequest(
                source_type=BacktestDataSourceType.CSV,
                path="/data/btc.csv",
            ),
        )
        session = BacktestSession(
            id="bt_101",
            ticker_symbol="BTC_USD",
            request=request,
            status=BacktestSessionStatus.COMPLETED,
            created_at=datetime(2026, 9, 10, 0, 0, 0, tzinfo=timezone.utc),
        )
        result = BacktestResult(
            session_id="bt_101",
            ticker_symbol="BTC_USD",
            initial_balance=Decimal("10000.0"),
            final_balance=Decimal("10500.0"),
            final_equity=Decimal("10750.0"),
            execution=ExecutionConfiguration(),
        )

        repo.list_sessions.return_value = [session]
        repo.get_result.return_value = result
        repo.get_result_metrics.return_value = {"return_pct": "7.5"}

        client = TestClient(build_app(db_manager))
        response = client.get("/api/v1/backtests")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["session_id"], "bt_101")
        self.assertEqual(data[0]["ticker_symbol"], "BTC_USD")
        self.assertEqual(data[0]["final_equity"], "10750.0")
        self.assertEqual(data[0]["metrics"]["return_pct"], "7.5")

    def test_get_backtest_endpoint_found(self):
        db_manager, repo = self._setup_db_manager()

        request = BacktestRequest(
            ticker_symbol="BTC_USD",
            initial_balance=Decimal("10000.0"),
        )
        session = BacktestSession(
            id="bt_101",
            ticker_symbol="BTC_USD",
            request=request,
            status=BacktestSessionStatus.COMPLETED,
            created_at=datetime(2026, 9, 10, 0, 0, 0, tzinfo=timezone.utc),
        )
        result = BacktestResult(
            session_id="bt_101",
            ticker_symbol="BTC_USD",
            initial_balance=Decimal("10000.0"),
            final_balance=Decimal("10500.0"),
            final_equity=Decimal("10750.0"),
            execution=ExecutionConfiguration(latency_ms=500.0, slippage_ticks=2, fee_rate=Decimal("0.001")),
        )

        repo.get_session.return_value = session
        repo.get_result.return_value = result
        repo.get_result_metrics.return_value = {"return_pct": "7.5"}

        client = TestClient(build_app(db_manager))
        response = client.get("/api/v1/backtests/bt_101")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["session_id"], "bt_101")
        self.assertEqual(data["final_equity"], "10750.0")
        self.assertEqual(data["execution_config"]["latency_ms"], 500.0)

    def test_get_backtest_endpoint_not_found(self):
        db_manager, repo = self._setup_db_manager()
        repo.get_session.return_value = None

        client = TestClient(build_app(db_manager))
        response = client.get("/api/v1/backtests/non_existent")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()

