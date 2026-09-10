from decimal import Decimal
from unittest.mock import MagicMock, Mock

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    ExecutionConfiguration,
)
from src.agent.backtest.backtest_service import BacktestService
from src.database import NoopDatabaseManager


def _make_service(runner=None):
    source = BacktestDataSourceRequest(
        source_type=BacktestDataSourceType.CSV, path="/data"
    )
    return BacktestService(
        runner=runner or Mock(),
        data_source_request=source,
        initial_balance=Decimal("10000.0"),
        execution=ExecutionConfiguration(),
        db_manager=NoopDatabaseManager(),
    )


class TestBacktestService:
    def test_build_request_carries_source(self):
        service = _make_service()

        request = service.build_request("BTC_USD")

        assert request.ticker_symbol == "BTC_USD"
        assert request.data_source.source_type == BacktestDataSourceType.CSV
        assert request.data_source.path == "/data"
        assert request.start_time is None
        assert request.end_time is None
        assert request.initial_balance == Decimal("10000.0")

    def test_build_request_with_market_data_source(self):
        service = _make_service()

        request = service.build_request("BTC_USD", source_type=BacktestDataSourceType.MARKET_DATA)

        assert request.data_source.source_type == BacktestDataSourceType.MARKET_DATA
        assert request.data_source.path is None

    def test_run_is_canonical_and_stores_session(self):
        runner = Mock()
        result = object()
        runner.run_session.return_value = result
        service = _make_service(runner=runner)

        request = service.build_request("BTC_USD")
        out = service.run(request)

        assert out is result
        runner.run_session.assert_called_once()
        session = runner.run_session.call_args[0][0]
        assert session.request == request
        assert service.get(session.id).request == request
        assert service.result(session.id) is result

    def test_run_persists_to_database_when_db_manager_provided(self):
        runner = Mock()
        result = Mock()
        result.initial_balance = Decimal("10000.0")
        result.final_equity = Decimal("10500.0")
        result.portfolio_snapshots = []
        result.fills = []
        result.orders = []
        runner.run_session.return_value = result

        db_manager = MagicMock()
        uow = MagicMock()
        repo = MagicMock()
        db_manager.get_unit_of_work.return_value.__enter__.return_value = uow
        uow.get_repository.return_value = repo

        source = BacktestDataSourceRequest(source_type=BacktestDataSourceType.CSV, path="/data")
        service = BacktestService(
            runner=runner,
            data_source_request=source,
            initial_balance=Decimal("10000.0"),
            execution=ExecutionConfiguration(),
            db_manager=db_manager,
        )

        request = service.build_request("BTC_USD")
        out = service.run(request)

        assert out is result
        repo.save_session.assert_called_once()
        repo.save_result.assert_called_once()

    def test_get_and_result_fall_back_to_database(self):
        db_manager = MagicMock()
        uow = MagicMock()
        repo = MagicMock()
        db_manager.get_unit_of_work.return_value.__enter__.return_value = uow
        uow.get_repository.return_value = repo

        db_session = Mock()
        db_result = Mock()
        repo.get_session.return_value = db_session
        repo.get_result.return_value = db_result
        repo.list_sessions.return_value = [db_session]

        source = BacktestDataSourceRequest(source_type=BacktestDataSourceType.CSV, path="/data")
        service = BacktestService(
            runner=Mock(),
            data_source_request=source,
            initial_balance=Decimal("10000.0"),
            execution=ExecutionConfiguration(),
            db_manager=db_manager,
        )

        assert service.get("bt_db_123") is db_session
        assert service.result("bt_db_123") is db_result
        assert service.list_sessions() == [db_session]

