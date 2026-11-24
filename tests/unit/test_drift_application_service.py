from __future__ import annotations

from decimal import Decimal
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.backtest.analysis.drift_detector import DriftReport
from src.server.routes.drift_routes import create_drift_router
from src.server.services.drift_application_service import (
    DriftApplicationService,
    extract_quote_currency,
)


def _sample_report(drifted: bool = True) -> DriftReport:
    return DriftReport(
        ticker_symbol="BTC_USD",
        simulated_fill_count=5,
        live_fill_count=4,
        simulated_quantity=Decimal("0.5"),
        live_quantity=Decimal("0.4"),
        simulated_average_price=Decimal("50000"),
        live_average_price=Decimal("50500"),
        fill_count_drift=1,
        quantity_drift=Decimal("0.1"),
        price_drift=Decimal("-500"),
        drifted=drifted,
        window_start="2026-10-01T00:00:00Z",
        window_end="2026-10-31T00:00:00Z",
        partial_fill_legs_merged=1,
        simulated_fees=Decimal("12.5"),
        live_fees=Decimal("15.0"),
        fee_drift=Decimal("-2.5"),
    )


def _make_app(service: DriftApplicationService) -> TestClient:
    app = FastAPI()
    app.state.drift_service = service
    app.include_router(create_drift_router())
    return TestClient(app)


def test_extract_quote_currency_from_underscore_pair():
    assert extract_quote_currency("BTC_USD") == "USD"


def test_extract_quote_currency_defaults_for_equity_symbol():
    assert extract_quote_currency("SPY") == "USD"


def test_get_snapshot_returns_none_before_first_run():
    service = DriftApplicationService(detect_fn=lambda _: _sample_report())
    assert service.get_snapshot("BTC_USD") is None


def test_get_snapshot_does_not_leak_across_different_commits():
    service = DriftApplicationService(detect_fn=lambda _: _sample_report())
    service.run_drift_check("BTC_USD", commit_hash="aaaa1111bbbb2222")
    assert service.get_snapshot("BTC_USD", commit_hash="cccc3333dddd4444") is None


def test_run_drift_check_caches_snapshot_for_subsequent_get():
    vcs = Mock()
    vcs.resolve_ref.return_value = "abc12345"
    service = DriftApplicationService(detect_fn=lambda _: _sample_report(), vcs_service=vcs)

    service.run_drift_check("BTC_USD")
    cached = service.get_snapshot("BTC_USD")

    assert cached is not None and cached.commit_hash == "abc12345"


def test_run_drift_check_builds_attribution_factors():
    service = DriftApplicationService(detect_fn=lambda _: _sample_report())
    snapshot = service.run_drift_check("BTC_USD")
    categories = [f.category for f in snapshot.attribution_factors]

    assert categories == ["price_slippage", "fees", "fill_count", "quantity"]


def test_run_drift_check_raises_when_detector_unavailable():
    service = DriftApplicationService(detect_fn=None)
    with pytest.raises(RuntimeError):
        service.run_drift_check("BTC_USD")


def test_drift_route_returns_404_when_no_snapshot_cached():
    client = _make_app(DriftApplicationService(detect_fn=lambda _: _sample_report()))
    response = client.get("/api/v1/drift/BTC_USD")
    assert response.status_code == 404


def test_drift_run_route_returns_snapshot_payload():
    client = _make_app(DriftApplicationService(detect_fn=lambda _: _sample_report()))
    response = client.post("/api/v1/drift/BTC_USD/run")
    assert response.status_code == 200 and response.json()["fill_count_drift"] == 1


def _report_with_simulated_curve() -> DriftReport:
    return DriftReport(
        ticker_symbol="BTC_USD",
        simulated_fill_count=2,
        live_fill_count=0,
        simulated_quantity=Decimal("0.2"),
        live_quantity=Decimal("0"),
        simulated_average_price=Decimal("50000"),
        live_average_price=None,
        fill_count_drift=2,
        quantity_drift=Decimal("0.2"),
        price_drift=None,
        drifted=True,
        window_start="2026-10-01T00:00:00+00:00",
        window_end="2026-10-02T00:00:00+00:00",
        simulated_pnl=Decimal("120.5"),
        simulated_equity_curve=(
            ("2026-10-01T00:00:00+00:00", 0.0),
            ("2026-10-01T12:00:00+00:00", 50.0),
            ("2026-10-02T00:00:00+00:00", 120.5),
        ),
    )


def test_run_drift_check_plots_flat_zero_live_pnl_when_no_live_fills():
    perf_service = Mock()
    perf_service.calculate_performance.return_value = Mock(summary=None, equity_curve=[])
    service = DriftApplicationService(
        detect_fn=lambda _: _report_with_simulated_curve(),
        asset_performance_service=perf_service,
    )

    snapshot = service.run_drift_check("BTC_USD")

    assert [(pt.simulated_cumulative_pnl, pt.live_cumulative_pnl) for pt in snapshot.equity_series] == [
        (0.0, 0.0),
        (50.0, 0.0),
        (120.5, 0.0),
    ]


def test_run_drift_check_sets_live_pnl_zero_when_no_live_fills_and_simulated_curve_exists():
    perf_service = Mock()
    perf_service.calculate_performance.return_value = Mock(summary=None, equity_curve=[])
    service = DriftApplicationService(
        detect_fn=lambda _: _report_with_simulated_curve(),
        asset_performance_service=perf_service,
    )

    snapshot = service.run_drift_check("BTC_USD")

    assert snapshot.live_pnl == 0.0


def test_run_drift_check_aligns_live_equity_points_onto_simulated_curve():
    perf_service = Mock()
    perf_service.calculate_performance.return_value = Mock(
        summary=Mock(realized_pnl="40.0"),
        equity_curve=[
            Mock(timestamp="2026-10-01T10:00:00+00:00", cumulative_pnl="40.0"),
        ],
    )
    service = DriftApplicationService(
        detect_fn=lambda _: _report_with_simulated_curve(),
        asset_performance_service=perf_service,
    )

    snapshot = service.run_drift_check("BTC_USD")

    assert [pt.live_cumulative_pnl for pt in snapshot.equity_series] == [0.0, 40.0, 40.0]


def test_run_drift_check_forwards_commit_hash_to_detect_fn():
    seen: list[tuple[str, str | None]] = []

    def _detect(symbol: str, commit_hash: str | None = None) -> DriftReport:
        seen.append((symbol, commit_hash))
        return _sample_report()

    service = DriftApplicationService(detect_fn=_detect)
    service.run_drift_check("BTC_USD", commit_hash="exp_commit_123")

    assert seen == [("BTC_USD", "exp_commit_123")]
