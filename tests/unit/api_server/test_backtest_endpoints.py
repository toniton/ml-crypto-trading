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
from src.recorder.market_data_store import MarketDataStore
from src.server.app import ChatApp
from src.vcs.application.service import VCSService
from tests.unit.agent.fakes import FakeLlmAdapter


def build_app(db_manager):
    vcs = MagicMock(spec=VCSService)
    return ChatApp.create(
        agent=AgentGateway(FakeLlmAdapter(chunks=["ok"]), vcs=vcs),
        event_bus=MessageEventBus(),
        db_manager=db_manager,
        market_data_store=MarketDataStore(),
        vcs=vcs,
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

    def test_upload_dataset_endpoint(self):
        db_manager, _ = self._setup_db_manager()
        client = TestClient(build_app(db_manager))

        csv_content = b"timestamp,open,high,low,close,volume\n2026-01-01T00:00:00,100,105,95,102,1000\n2026-01-01T01:00:00,102,108,101,107,1500\n"
        response = client.post(
            "/api/v1/backtests/datasets",
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["filename"], "test.csv")
        self.assertEqual(data["row_count"], 2)
        self.assertTrue(bool(data["sha256"]))

        list_resp = client.get("/api/v1/backtests/datasets")
        self.assertEqual(list_resp.status_code, 200)
        datasets = list_resp.json()
        self.assertTrue(any(d["id"] == data["id"] for d in datasets))

    def test_upload_semicolon_delimited_dataset_with_extra_columns(self):
        db_manager, _ = self._setup_db_manager()
        client = TestClient(build_app(db_manager))

        csv_content = (
            b"timeOpen;timeClose;timeHigh;timeLow;name;open;high;low;close;volume;marketCap;timestamp\n"
            b"2026-01-01T00:00:00;2026-01-01T00:01:00;105;95;Bitcoin;100;105;95;102;1000;2000000;2026-01-01T00:00:00Z\n"
            b"2026-01-01T00:01:00;2026-01-01T00:02:00;108;101;Bitcoin;102;108;101;107;1500;2000000;2026-01-01T00:01:00Z\n"
        )
        response = client.post(
            "/api/v1/backtests/datasets",
            files={"file": ("btc_semicolon.csv", csv_content, "text/csv")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["filename"], "btc_semicolon.csv")
        self.assertEqual(data["row_count"], 2)
        self.assertTrue(bool(data["sha256"]))



if __name__ == "__main__":
    unittest.main()


