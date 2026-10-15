import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from api.interfaces.market_data import MarketData
from src.database.dao.backtest_session_dao import BacktestSessionDao
from src.database.dao.experiment_dao import ExperimentDao
from src.database.dao.runtime_incident_dao import RuntimeErrorEventDao, RuntimeIncidentDao
from src.database.dao.timeline_item_dao import TimelineItemDao
from src.recorder.market_data_store import MarketDataStore
from src.retention.handlers import (
    ApplicationLogHandler,
    ExperimentArtifactHandler,
    MarketDataBufferHandler,
    MarketDataHandler,
    ReportHandler,
    RetentionContext,
    RuntimeAlertHandler,
    TableRetentionHandler,
)
from src.retention.models import DataCategory, RetentionMode, RetentionPolicy


class HandlerTestFixtures:
    @staticmethod
    def naive_now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def make_policy(
        category: DataCategory, mode: RetentionMode, period: str = "30d"
    ) -> RetentionPolicy:
        return RetentionPolicy(
            policy_id=category.value.lower(),
            data_category=category,
            retention_period=period,
            retention_mode=mode,
        )

    @staticmethod
    def make_context(
        session, policy, cutoff, dry_run=False, now=None, batch_size=100
    ) -> RetentionContext:
        return RetentionContext(
            session=session,
            policy=policy,
            now=now or HandlerTestFixtures.naive_now(),
            cutoff=cutoff,
            batch_size=batch_size,
            dry_run=dry_run,
        )

    @staticmethod
    def market_data(timestamp: int, close: str) -> MarketData:
        return MarketData(
            close_price=Decimal(close),
            high_price=Decimal(close),
            low_price=Decimal(close),
            volume=Decimal("100"),
            timestamp=float(timestamp),
        )


naive_now = HandlerTestFixtures.naive_now
make_policy = HandlerTestFixtures.make_policy
make_context = HandlerTestFixtures.make_context
_market_data = HandlerTestFixtures.market_data


class TestTableRetentionHandler:
    def test_delete_removes_old_rows(self, db_manager):
        now = naive_now()
        cutoff = now - timedelta(days=30)
        with db_manager.get_unit_of_work() as uow:
            session = uow.session
            session.add(TimelineItemDao(id="old", timestamp=now - timedelta(days=100), category="TRADING", title="old"))
            session.add(TimelineItemDao(id="new", timestamp=now, category="TRADING", title="new"))
            session.flush()

            handler = TableRetentionHandler(DataCategory.TRACE, TimelineItemDao, TimelineItemDao.timestamp)
            policy = make_policy(DataCategory.TRACE, RetentionMode.DELETE)

            preview = handler.evaluate(make_context(session, policy, cutoff, dry_run=True))
            assert preview.eligible == 1
            assert preview.deleted == 0
            assert session.query(TimelineItemDao).count() == 2

            outcome = handler.execute(make_context(session, policy, cutoff, dry_run=False))
            assert outcome.deleted == 1
            assert session.query(TimelineItemDao).count() == 1

    def test_keep_mode_skips_everything(self, db_manager):
        now = naive_now()
        with db_manager.get_unit_of_work() as uow:
            session = uow.session
            session.add(TimelineItemDao(id="old", timestamp=now - timedelta(days=100), category="TRADING", title="old"))
            session.flush()
            handler = TableRetentionHandler(DataCategory.TRACE, TimelineItemDao, TimelineItemDao.timestamp)
            policy = make_policy(DataCategory.TRACE, RetentionMode.KEEP)
            outcome = handler.execute(make_context(session, policy, cutoff=None))
            assert outcome.deleted == 0
            assert outcome.skipped == 1
            assert outcome.skipped_reasons[0].reason == "KEEP"


class TestReportHandler:
    def test_skips_reports_referenced_by_experiments(self, db_manager):
        now = naive_now()
        cutoff = now - timedelta(days=30)
        with db_manager.get_unit_of_work() as uow:
            session = uow.session
            session.add(
                ExperimentDao(
                    id="exp-1",
                    name="experiment",
                    ticker_symbol="BTC_USD",
                    branch_id="branch-1",
                    base_commit_hash="abc",
                    status="COMPLETED",
                    spec={"candidates": []},
                    run_bindings=[{"backtest_session_id": "sess-keep"}],
                )
            )
            session.add(BacktestSessionDao(id="sess-keep", ticker_symbol="BTC_USD", status="COMPLETED", created_at=now - timedelta(days=100)))
            session.add(BacktestSessionDao(id="sess-drop", ticker_symbol="BTC_USD", status="COMPLETED", created_at=now - timedelta(days=100)))
            session.flush()

            handler = ReportHandler()
            policy = make_policy(DataCategory.REPORT, RetentionMode.DELETE, "30d")
            outcome = handler.execute(make_context(session, policy, cutoff))

            assert outcome.eligible == 1
            assert outcome.skipped == 1
            assert outcome.deleted == 1
            assert session.query(BacktestSessionDao).filter(BacktestSessionDao.id == "sess-keep").count() == 1
            assert session.query(BacktestSessionDao).filter(BacktestSessionDao.id == "sess-drop").count() == 0

    def test_deletes_reports_in_batches(self, db_manager):
        now = naive_now()
        cutoff = now - timedelta(days=30)
        with db_manager.get_unit_of_work() as uow:
            session = uow.session
            for i in range(5):
                session.add(
                    BacktestSessionDao(
                        id=f"sess-batch-{i}",
                        ticker_symbol="BTC_USD",
                        status="COMPLETED",
                        created_at=now - timedelta(days=100),
                    )
                )
            session.flush()

            handler = ReportHandler()
            policy = make_policy(DataCategory.REPORT, RetentionMode.DELETE, "30d")
            ctx = make_context(session, policy, cutoff, batch_size=2)
            outcome = handler.execute(ctx)

            assert outcome.eligible == 5
            assert outcome.deleted == 5
            assert session.query(BacktestSessionDao).filter(BacktestSessionDao.id.startswith("sess-batch-")).count() == 0


class TestMarketDataHandler:
    def test_deletes_unreferenced_old_datasets(self, db_manager, tmp_path):
        now = naive_now()
        cutoff = now - timedelta(days=30)
        old_ts = (now - timedelta(days=100)).timestamp()

        for dataset_id in ("aabbccddeeff", "112233445566"):
            (tmp_path / f"{dataset_id}.csv").write_text("timestamp,open\n1,1\n", encoding="utf-8")
            (tmp_path / f"{dataset_id}.meta.json").write_text("{}", encoding="utf-8")

        for name in ("aabbccddeeff.csv", "aabbccddeeff.meta.json", "112233445566.csv", "112233445566.meta.json"):
            os.utime(tmp_path / name, (old_ts, old_ts))

        with db_manager.get_unit_of_work() as uow:
            session = uow.session
            session.add(
                BacktestSessionDao(
                    id="sess-1",
                    ticker_symbol="BTC_USD",
                    status="COMPLETED",
                    config={"data_source": {"source_id": "112233445566"}},
                    created_at=now - timedelta(days=100),
                )
            )
            session.flush()

            handler = MarketDataHandler(datasets_dir=str(tmp_path))
            policy = make_policy(DataCategory.MARKET_DATA, RetentionMode.DELETE, "30d")
            outcome = handler.execute(make_context(session, policy, cutoff))

            assert outcome.eligible == 1
            assert outcome.skipped == 1
            assert outcome.storage_bytes and outcome.storage_bytes > 0
            assert not (tmp_path / "aabbccddeeff.csv").exists()
            assert (tmp_path / "112233445566.csv").exists()



class TestMarketDataBufferHandler:
    def test_prunes_observations_older_than_policy(self):
        now = naive_now()
        cutoff = now - timedelta(days=30)
        store = MarketDataStore(max_age=None)
        store.record("BTC_USD", _market_data(int((now - timedelta(days=100)).timestamp()), "100"))
        store.record("BTC_USD", _market_data(int(now.timestamp()), "200"))

        handler = MarketDataBufferHandler(store)
        policy = make_policy(DataCategory.MARKET_DATA_BUFFER, RetentionMode.DELETE, "30d")

        preview = handler.evaluate(make_context(None, policy, cutoff, dry_run=True))
        assert preview.examined == 2
        assert preview.eligible == 1
        assert store.size() == 2

        outcome = handler.execute(make_context(None, policy, cutoff, dry_run=False))
        assert outcome.deleted == 1
        assert store.size() == 1

    def test_keep_mode_does_not_prune(self):
        now = naive_now()
        store = MarketDataStore(max_age=None)
        store.record("BTC_USD", _market_data(int((now - timedelta(days=400)).timestamp()), "100"))

        handler = MarketDataBufferHandler(store)
        policy = make_policy(DataCategory.MARKET_DATA_BUFFER, RetentionMode.KEEP, "30d")
        outcome = handler.execute(make_context(None, policy, cutoff=None))

        assert outcome.deleted == 0
        assert store.size() == 1

    def test_sync_policy_updates_store_retention(self):
        store = MarketDataStore(max_age=None)
        handler = MarketDataBufferHandler(store)
        policy = make_policy(DataCategory.MARKET_DATA_BUFFER, RetentionMode.DELETE, "6h")

        handler.sync_policy(policy)

        assert store.max_age == timedelta(hours=6)


class TestRuntimeAlertHandler:
    def test_deletes_old_incidents_and_events(self, db_manager):
        now = naive_now()
        cutoff = now - timedelta(days=180)
        with db_manager.get_unit_of_work() as uow:
            session = uow.session
            session.add(
                RuntimeIncidentDao(
                    id="inc-old",
                    fingerprint="fp1",
                    severity="HIGH",
                    status="RESOLVED",
                    category="TRADING",
                    component="engine",
                    first_seen=now - timedelta(days=200),
                    last_seen=now - timedelta(days=200),
                )
            )
            session.add(
                RuntimeIncidentDao(
                    id="inc-new",
                    fingerprint="fp2",
                    severity="LOW",
                    status="OPEN",
                    category="TRADING",
                    component="engine",
                    first_seen=now - timedelta(days=10),
                    last_seen=now - timedelta(days=10),
                )
            )
            session.add(
                RuntimeErrorEventDao(
                    id="evt-old",
                    incident_id="inc-old",
                    timestamp=now - timedelta(days=200),
                    severity="HIGH",
                    component="engine",
                    error_type="ValueError",
                    message="Old error",
                    fingerprint="fp1",
                )
            )
            session.add(
                RuntimeErrorEventDao(
                    id="evt-new",
                    incident_id="inc-new",
                    timestamp=now - timedelta(days=10),
                    severity="LOW",
                    component="engine",
                    error_type="KeyError",
                    message="New error",
                    fingerprint="fp2",
                )
            )
            session.flush()

            handler = RuntimeAlertHandler()
            policy = make_policy(DataCategory.RUNTIME_ALERT, RetentionMode.AGGREGATE_THEN_DELETE, "180d")

            preview = handler.evaluate(make_context(session, policy, cutoff, dry_run=True))
            assert preview.eligible == 2
            assert preview.examined == 4

            outcome = handler.execute(make_context(session, policy, cutoff, dry_run=False))
            assert outcome.deleted == 2
            assert outcome.aggregated == 2
            assert session.query(RuntimeIncidentDao).count() == 1
            assert session.query(RuntimeErrorEventDao).count() == 1


class TestExperimentArtifactHandler:
    def test_compacts_completed_experiment_report(self, db_manager):
        now = naive_now()
        cutoff = now - timedelta(days=90)
        with db_manager.get_unit_of_work() as uow:
            session = uow.session
            session.add(
                ExperimentDao(
                    id="exp-old-done",
                    name="Completed Old Experiment",
                    ticker_symbol="BTC_USD",
                    branch_id="b1",
                    base_commit_hash="h1",
                    status="COMPLETED",
                    spec={},
                    created_at=now - timedelta(days=100),
                    report={
                        "summary": {"total_trades": 100},
                        "verdict": "PROMOTED",
                        "status": "COMPLETED",
                        "completed_at": (now - timedelta(days=100)).isoformat(),
                        "heavy_trades_list": [{"trade_id": i} for i in range(500)],
                        "heavy_regime_matrix": {"matrix": [[1, 2], [3, 4]]},
                    },
                )
            )
            session.add(
                ExperimentDao(
                    id="exp-running",
                    name="Running Experiment",
                    ticker_symbol="BTC_USD",
                    branch_id="b2",
                    base_commit_hash="h2",
                    status="RUNNING",
                    spec={},
                    created_at=now - timedelta(days=100),
                    report={"heavy_trades_list": [1, 2, 3]},
                )
            )
            session.flush()

            handler = ExperimentArtifactHandler()
            policy = make_policy(DataCategory.EXPERIMENT_ARTIFACT, RetentionMode.DELETE, "90d")

            outcome = handler.execute(make_context(session, policy, cutoff, dry_run=False))
            assert outcome.deleted == 1

            compacted = session.query(ExperimentDao).filter(ExperimentDao.id == "exp-old-done").first()
            assert "summary" in compacted.report
            assert "verdict" in compacted.report
            assert "heavy_trades_list" not in compacted.report
            assert "heavy_regime_matrix" not in compacted.report

            running = session.query(ExperimentDao).filter(ExperimentDao.id == "exp-running").first()
            assert "heavy_trades_list" in running.report


class TestApplicationLogHandler:
    def test_deletes_only_rotated_logs_older_than_cutoff(self, tmp_path):
        now = naive_now()
        cutoff = now - timedelta(days=30)
        old_ts = (now - timedelta(days=45)).timestamp()
        recent_ts = (now - timedelta(days=5)).timestamp()

        old_rotated = tmp_path / "application-2026-08.log.1"
        recent_rotated = tmp_path / "application-2026-10.log.1"
        active_log = tmp_path / "application.log"
        other_file = tmp_path / "notes.txt"

        for f in (old_rotated, recent_rotated, active_log, other_file):
            f.write_text("log content", encoding="utf-8")

        os.utime(old_rotated, (old_ts, old_ts))
        os.utime(recent_rotated, (recent_ts, recent_ts))
        os.utime(active_log, (old_ts, old_ts))

        handler = ApplicationLogHandler(log_dir=str(tmp_path))
        policy = make_policy(DataCategory.APPLICATION_LOG, RetentionMode.DELETE, "30d")

        preview = handler.evaluate(make_context(None, policy, cutoff, dry_run=True))
        assert preview.examined == 2
        assert preview.eligible == 1
        assert old_rotated.exists()

        outcome = handler.execute(make_context(None, policy, cutoff, dry_run=False))
        assert outcome.deleted == 1
        assert not old_rotated.exists()
        assert recent_rotated.exists()
        assert active_log.exists()
        assert other_file.exists()

