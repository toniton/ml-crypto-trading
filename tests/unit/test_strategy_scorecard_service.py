from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.interfaces.scorecard import LifecycleStage
from src.database.repositories.providers.postgres_scorecard_snapshot_repository import (
    PostgresScorecardSnapshotRepository,
)
from src.server.routes.scorecard_routes import create_scorecard_router
from src.server.services.drift_application_service import DriftApplicationService
from src.server.services.strategy_scorecard_service import StrategyScorecardService


class _FakeSnapshotRepo:
    def __init__(self) -> None:
        self._records = {}

    def save_snapshot(self, record):
        self._records[record.snapshot_id] = record
        return record

    def get_snapshot(self, snapshot_id: str):
        return self._records.get(snapshot_id)

    def list_snapshots(self, symbol=None, limit=50):
        records = list(self._records.values())
        if symbol:
            records = [r for r in records if r.scorecard.symbol == symbol]
        return [
            StrategyScorecardService._to_snapshot_summary(r)  # pylint: disable=protected-access
            for r in records[:limit]
        ]


def _build_db_manager(sessions=None, metrics=None, result=None):
    bt_repo = Mock()
    bt_repo.list_sessions.return_value = sessions or []
    bt_repo.get_result_metrics.return_value = metrics or {}
    bt_repo.get_result.return_value = result
    snap_repo = _FakeSnapshotRepo()

    def _get_repo(repo_cls):
        if repo_cls is PostgresScorecardSnapshotRepository:
            return snap_repo
        return bt_repo

    uow = MagicMock()
    uow.__enter__.return_value.get_repository.side_effect = _get_repo
    db_manager = Mock()
    db_manager.get_unit_of_work.return_value = uow
    return db_manager


def _build_service(
        sessions=None,
        bt_metrics=None,
        wf_runs=None,
        sim_runs=None,
        sim_report=None,
        experiments=None,
        live_perf=None,
        config_assets=None,
) -> StrategyScorecardService:
    vcs = Mock()
    vcs.resolve_ref.return_value = "deadbeef1234"
    vcs.get_commit.return_value = SimpleNamespace(message="Optimize RSI thresholds")

    wf = Mock()
    wf.list_runs.return_value = wf_runs or []

    sim_orch = Mock()
    sim_orch.list_simulated_runs.return_value = sim_runs or []

    sim_rep = Mock()
    sim_rep.get_report_by_run.return_value = sim_report

    exp = Mock()
    exp.list_experiments.return_value = experiments or []

    perf = Mock()
    if live_perf is not None:
        perf.calculate_performance.return_value = live_perf
    else:
        perf.calculate_performance.side_effect = RuntimeError("no live data")

    cfg = Mock()
    cfg.load_config.return_value = {"assets": config_assets or [{"ticker": "BTC_USD"}]}

    return StrategyScorecardService(
        db_manager=_build_db_manager(sessions=sessions, metrics=bt_metrics),
        vcs_service=vcs,
        walk_forward_service=wf,
        simulation_orchestrator=sim_orch,
        simulation_report_service=sim_rep,
        experiment_service=exp,
        asset_performance_service=perf,
        drift_service=DriftApplicationService(detect_fn=None),
        configuration_service=cfg,
    )


def _sample_bt_session():
    return SimpleNamespace(
        id="bt-1",
        ticker_symbol="BTC_USD",
        status=SimpleNamespace(value="COMPLETED"),
        request=SimpleNamespace(initial_balance=Decimal("10000")),
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )


def test_empty_scorecard_defaults_to_draft_stage():
    service = _build_service()
    card = service.get_scorecard("BTC_USD")
    assert card.lifecycle.current_stage == LifecycleStage.DRAFT


def test_scorecard_advances_to_walk_forward_verified_when_bt_and_wf_complete():
    wf_runs = [
        {
            "run_id": "wf-1",
            "ticker_symbol": "BTC_USD",
            "status": "COMPLETED",
            "summary": {
                "in_sample_return_pct": 18.4,
                "out_of_sample_return_pct": 12.1,
                "max_out_of_sample_drawdown_pct": 6.5,
                "folds": [
                    {
                        "in_sample_trades": 40,
                        "out_of_sample_trades": 15,
                        "out_of_sample_win_rate_pct": 60.0,
                        "out_of_sample_profit_factor": 1.6,
                    }
                ],
            },
        }
    ]
    service = _build_service(
        sessions=[_sample_bt_session()],
        bt_metrics={"portfolio_risk": {"total_return_pct": 16.0, "max_drawdown_pct": 7.2}},
        wf_runs=wf_runs,
    )
    card = service.get_scorecard("BTC_USD")
    assert card.lifecycle.current_stage == LifecycleStage.WALK_FORWARD_VERIFIED


def test_scorecard_enables_promotion_when_paper_sim_passes_gate_b():
    sim_runs = [{"run_id": "sim-1", "ticker_symbol": "BTC_USD", "status": "COMPLETED"}]
    sim_report = {
        "metrics": {"total_return_pct": 4.2, "max_drawdown_pct": 2.1, "total_trades": 12},
        "gate_b_evaluation": {
            "gate_name": "Gate B: Simulation to Main",
            "decision": "PASS",
            "checks": [{"name": "min_trades", "status": "PASSED", "message": "ok"}],
        },
    }
    service = _build_service(sim_runs=sim_runs, sim_report=sim_report)
    card = service.get_scorecard("BTC_USD")
    assert card.lifecycle.can_promote_to_main is True


def test_list_scorecards_discovers_configured_symbols():
    service = _build_service(config_assets=[{"ticker": "BTC_USD"}, {"ticker": "ETH_USD"}])
    summaries = service.list_scorecards()
    assert [s.symbol for s in summaries] == ["BTC_USD", "ETH_USD"]


def test_scorecard_route_returns_asset_agnostic_fields():
    app = FastAPI()
    app.state.scorecard_service = _build_service()
    app.include_router(create_scorecard_router())
    client = TestClient(app)

    response = client.get("/api/v1/scorecards/BTC_USD")
    body = response.json()

    assert response.status_code == 200 and body["quote_currency"] == "USD" and body["commit_hash"] == "deadbeef1234"


def test_save_and_get_snapshot_preserves_immutable_record():
    service = _build_service()
    saved = service.save_snapshot(symbol="BTC_USD", trigger="manual")
    fetched = service.get_snapshot(saved.snapshot_id)
    assert fetched is not None and fetched.snapshot_id == saved.snapshot_id


def test_snapshot_routes_create_list_and_fetch_snapshot():
    app = FastAPI()
    app.state.scorecard_service = _build_service()
    app.include_router(create_scorecard_router())
    client = TestClient(app)

    created = client.post("/api/v1/scorecards/BTC_USD/snapshots").json()
    listed = client.get("/api/v1/scorecards/snapshots?symbol=BTC_USD").json()
    fetched = client.get(f"/api/v1/scorecards/snapshots/{created['snapshot_id']}").json()

    assert len(listed) == 1 and fetched["snapshot_id"] == created["snapshot_id"]


def test_snapshot_route_returns_404_for_unknown_id():
    app = FastAPI()
    app.state.scorecard_service = _build_service()
    app.include_router(create_scorecard_router())
    client = TestClient(app)

    response = client.get("/api/v1/scorecards/snapshots/sc_missing")
    assert response.status_code == 404


def test_scorecard_strictly_scopes_backtest_to_requested_commit():
    other_commit_session = _sample_bt_session()
    other_commit_session.request.configuration = SimpleNamespace(vcs_commit_hash="aaaa1111bbbb2222")
    service = _build_service(
        sessions=[other_commit_session],
        bt_metrics={"portfolio_risk": {"total_return_pct": 16.0}},
    )
    card = service.get_scorecard("BTC_USD", commit_hash="cccc3333dddd4444")
    assert card.lifecycle.current_stage == LifecycleStage.DRAFT


def test_scorecard_matches_backtest_session_commit_hash_and_zero_win_rate():
    bt_session = _sample_bt_session()
    bt_session.commit_hash = "cddfe5aa85797258bbc003f6cf21ec55597da8470"
    service = _build_service(
        sessions=[bt_session],
        bt_metrics={
            "percentage_return": "-0.04",
            "max_drawdown_pct": "0.04",
            "sharpe_ratio": "-86.93",
            "win_rate_pct": "0.00",
            "profit_factor": "0.00",
            "total_trades": 5,
        },
    )
    card = service.get_scorecard("BTC_USD", commit_hash="cddfe5aa85797258bbc003f6cf21ec55597da8470")
    bt_stage = next(s for s in card.stages if s.stage == "backtest")

    assert bt_stage.status == "available"
    assert bt_stage.return_pct == -0.04
    assert bt_stage.max_drawdown_pct == 0.04
    assert bt_stage.win_rate_pct == 0.0
    assert bt_stage.trade_count == 5
