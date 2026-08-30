from datetime import datetime, timezone
from decimal import Decimal

import pytest

from api.interfaces.backtest_request import (
    BacktestRequest,
    ExecutionConfiguration,
    MarketDataConfiguration,
)
from src.backtest.domain.result import BacktestResult
from src.backtest.domain.session import BacktestSession, BacktestSessionStatus


def _make_request(**overrides) -> BacktestRequest:
    kwargs = {
        "asset": "BTC_USD",
        "start_time": datetime(2026, 8, 1, tzinfo=timezone.utc),
        "end_time": datetime(2026, 8, 2, tzinfo=timezone.utc),
        "market_data": MarketDataConfiguration(data_source="/tmp/data"),
    }
    kwargs.update(overrides)
    return BacktestRequest(**kwargs)


def _make_result() -> BacktestResult:
    return BacktestResult(
        session_id="bt_x",
        asset="BTC_USD",
        initial_balance=Decimal("10000.0"),
        final_balance=Decimal("10000.0"),
        final_equity=Decimal("10000.0"),
        execution=ExecutionConfiguration(),
    )


class TestBacktestSession:
    def test_new_session_is_created(self):
        session = BacktestSession(asset="BTC_USD", request=_make_request())

        assert session.asset == "BTC_USD"
        assert session.status == BacktestSessionStatus.CREATED
        assert session.started_at is None
        assert session.completed_at is None

    def test_ids_are_unique(self):
        first = BacktestSession(asset="BTC_USD", request=_make_request())
        second = BacktestSession(asset="BTC_USD", request=_make_request())

        assert first.id != second.id

    def test_lifecycle_to_completed(self):
        session = BacktestSession(asset="BTC_USD", request=_make_request())

        session.start()
        assert session.status == BacktestSessionStatus.RUNNING
        assert session.started_at is not None

        session.complete()
        assert session.status == BacktestSessionStatus.COMPLETED
        assert session.completed_at is not None
        assert session.duration is not None
        assert session.duration >= 0

    def test_initialize_transitions_to_initializing(self):
        session = BacktestSession(asset="BTC_USD", request=_make_request())

        session.initialize()

        assert session.status == BacktestSessionStatus.INITIALIZING

    def test_result_is_none_by_default(self):
        session = BacktestSession(asset="BTC_USD", request=_make_request())

        assert session.result is None

    def test_complete_attaches_result(self):
        session = BacktestSession(asset="BTC_USD", request=_make_request())
        result = _make_result()

        session.complete(result)

        assert session.status == BacktestSessionStatus.COMPLETED
        assert session.result is result

    def test_attach_result(self):
        session = BacktestSession(asset="BTC_USD", request=_make_request())
        result = _make_result()

        session.attach_result(result)

        assert session.result is result
        assert session.status == BacktestSessionStatus.CREATED

    def test_fail_records_error(self):
        session = BacktestSession(asset="BTC_USD", request=_make_request())

        session.fail("boom")

        assert session.status == BacktestSessionStatus.FAILED
        assert session.error == "boom"
        assert session.completed_at is not None

    def test_cancel(self):
        session = BacktestSession(asset="BTC_USD", request=_make_request())

        session.cancel()

        assert session.status == BacktestSessionStatus.CANCELLED

    def test_duration_none_before_completion(self):
        session = BacktestSession(asset="BTC_USD", request=_make_request())
        session.start()

        assert session.duration is None


class TestBacktestRequest:
    def test_execution_defaults(self):
        config = ExecutionConfiguration()

        assert config.latency_ms == 500.0
        assert config.slippage_ticks == 2
        assert config.fee_rate == Decimal("0.001")

    def test_request_is_immutable(self):
        request = _make_request()

        with pytest.raises(Exception):
            request.asset = "ETH_USD"  # type: ignore[misc]

    def test_initial_balance_default(self):
        request = _make_request()

        assert request.initial_balance == Decimal("10000.0")
        assert request.configuration == {}
