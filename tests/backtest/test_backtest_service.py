from decimal import Decimal
from unittest.mock import Mock

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    ExecutionConfiguration,
)
from src.agent.backtest.backtest_service import BacktestService


def _make_service(runner=None):
    source = BacktestDataSourceRequest(
        source_type=BacktestDataSourceType.CSV, path="/data"
    )
    return BacktestService(
        runner=runner or Mock(),
        data_source_request=source,
        initial_balance=Decimal("10000.0"),
        execution=ExecutionConfiguration(),
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
