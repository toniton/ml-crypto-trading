import pytest

from src.configuration.retention_config import RetentionConfig
from src.database.repositories.providers.postgres_retention_repository import (
    PostgresRetentionRepository,
)
from src.retention.manager import (
    RetentionConfirmationRequired,
    RetentionManager,
    RetentionRunAlreadyInProgress,
)
from src.retention.models import RetentionAuditEventType, RetentionRunStatus


class TestRetentionManager:
    def make_manager(self, db_manager, dry_run=True):
        config = RetentionConfig(dry_run=dry_run)
        return RetentionManager(db_manager, config=config)

    def test_status_reports_configuration(self, db_manager):
        manager = self.make_manager(db_manager)
        status = manager.status()
        assert status["enabled"] is True
        assert status["schedule"] == "DAILY"
        assert status["dry_run"] is True
        assert status["grace_period"] == "7d"
        assert "next_run_at" in status

    def test_list_policies_returns_all_categories(self, db_manager):
        manager = self.make_manager(db_manager)
        policies = manager.list_policies()
        assert len(policies) == len(RetentionConfig().policies)
        assert all("policy_id" in policy for policy in policies)

    def test_preview_is_dry_run_and_persisted(self, db_manager):
        manager = self.make_manager(db_manager)
        run = manager.preview()
        assert run["dry_run"] is True
        assert run["status"] == RetentionRunStatus.COMPLETED.value
        assert len(run["categories"]) == len(RetentionConfig().policies)

        stored = manager.list_runs(limit=5)
        assert any(item["run_id"] == run["run_id"] for item in stored)

    def test_execute_honors_global_dry_run(self, db_manager):
        manager = self.make_manager(db_manager, dry_run=True)
        run = manager.execute(actor="tester")
        assert run["dry_run"] is True
        assert run["trigger"] == "MANUAL"

    def test_update_policy_requires_confirmation_when_shortening(self, db_manager):
        manager = self.make_manager(db_manager)
        with pytest.raises(RetentionConfirmationRequired):
            manager.update_policy("trace_events", retention_period="30d")

    def test_update_policy_with_confirmation_is_audited(self, db_manager):
        manager = self.make_manager(db_manager)
        updated = manager.update_policy(
            "trace_events", retention_period="30d", actor="ops", confirm=True
        )
        assert updated["retention_period"] == "30d"

        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            events = repository.list_audit_events(limit=10)
        assert any(event.event_type.value == "POLICY_UPDATED" for event in events)

    def test_update_unknown_policy_raises(self, db_manager):
        manager = self.make_manager(db_manager)
        with pytest.raises(KeyError):
            manager.update_policy("does_not_exist", enabled=False)

    def test_legal_hold_skips_category(self, db_manager):
        manager = self.make_manager(db_manager)
        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            from src.retention.models import DataCategory

            repository.add_hold(DataCategory.TRACE, reason="legal hold")
        run = manager.preview()
        trace = next(c for c in run["categories"] if c["data_category"] == "TRACE")
        assert any(reason["reason"] == "LEGAL_HOLD" for reason in trace["skipped_reasons"])

    def test_schedule_interval_supports_custom_duration_and_standard_names(self, db_manager):
        from datetime import timedelta
        manager_12h = RetentionManager(db_manager, config=RetentionConfig(schedule="12h"))
        assert manager_12h.schedule_interval() == timedelta(hours=12)

        manager_weekly = RetentionManager(db_manager, config=RetentionConfig(schedule="WEEKLY"))
        assert manager_weekly.schedule_interval() == timedelta(weeks=1)

    def test_handler_error_isolation_marks_partial_status(self, db_manager):
        from src.retention.handlers import KeepHandler
        from src.retention.models import DataCategory

        class FailingHandler(KeepHandler):
            def execute(self, ctx):
                raise RuntimeError("disk read timeout")

        manager = self.make_manager(db_manager, dry_run=False)
        manager._handlers[DataCategory.TRACE] = FailingHandler(DataCategory.TRACE)

        run = manager.execute(actor="test")
        assert run["status"] == RetentionRunStatus.PARTIAL.value
        trace_outcome = next(c for c in run["categories"] if c["data_category"] == "TRACE")
        assert any(
            r["reason"] == "ERROR" and "disk read timeout" in (r.get("detail") or "")
            for r in trace_outcome["skipped_reasons"]
        )

    def test_end_to_end_retention_execution(self, db_manager):
        from datetime import datetime, timedelta, timezone
        from src.database.dao.backtest_session_dao import BacktestSessionDao
        from src.database.dao.experiment_dao import ExperimentDao
        from src.database.dao.order_dao import OrderDao
        from src.database.dao.timeline_item_dao import TimelineItemDao

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cutoff_old = now - timedelta(days=400)

        with db_manager.get_unit_of_work() as uow:
            session = uow.session
            session.add(
                OrderDao(
                    uuid="ord-1",
                    provider_name="BINANCE",
                    ticker_symbol="BTC_USD",
                    trade_action="BUY",
                    quantity="1.0",
                    price="50000.0",
                    status="FILLED",
                    created_timestamp=cutoff_old,
                )
            )
            session.add(
                TimelineItemDao(
                    id="trace-old",
                    category="TRADING",
                    title="Old Trace",
                    timestamp=cutoff_old,
                )
            )
            session.add(
                ExperimentDao(
                    id="exp-active",
                    name="Active Experiment",
                    ticker_symbol="BTC_USD",
                    branch_id="b1",
                    base_commit_hash="c1",
                    status="COMPLETED",
                    spec={},
                    run_bindings=[{"backtest_session_id": "sess-referenced"}],
                    created_at=cutoff_old,
                    report={"summary": {"pnl": 100}, "heavy_data": [1, 2, 3]},
                )
            )
            session.add(
                BacktestSessionDao(
                    id="sess-referenced",
                    ticker_symbol="BTC_USD",
                    status="COMPLETED",
                    created_at=cutoff_old,
                )
            )
            session.add(
                BacktestSessionDao(
                    id="sess-orphaned",
                    ticker_symbol="BTC_USD",
                    status="COMPLETED",
                    created_at=cutoff_old,
                )
            )
            session.flush()

        manager = self.make_manager(db_manager, dry_run=False)
        manager.update_policy("trace_events", retention_mode="DELETE", confirm=True)
        run = manager.execute(actor="integration-test")

        assert run["status"] == RetentionRunStatus.COMPLETED.value
        assert run["dry_run"] is False

        with db_manager.get_unit_of_work() as uow:
            session = uow.session
            # Financial records are kept indefinitely
            assert session.query(OrderDao).filter(OrderDao.uuid == "ord-1").count() == 1
            # Old trace items are pruned
            assert session.query(TimelineItemDao).filter(TimelineItemDao.id == "trace-old").count() == 0
            # Referenced backtests are preserved
            assert session.query(BacktestSessionDao).filter(BacktestSessionDao.id == "sess-referenced").count() == 1
            # Orphaned backtests older than cutoff are deleted
            assert session.query(BacktestSessionDao).filter(BacktestSessionDao.id == "sess-orphaned").count() == 0
            # Experiment artifacts are compacted
            exp = session.query(ExperimentDao).filter(ExperimentDao.id == "exp-active").first()
            assert "summary" in exp.report
            assert "heavy_data" not in exp.report

    def test_disabled_retention_persists_completed_terminal_status_and_audit(self, db_manager):
        config = RetentionConfig(enabled=False)
        manager = RetentionManager(db_manager, config=config)
        run = manager.execute(actor="disabled-tester")

        assert run["status"] == RetentionRunStatus.COMPLETED.value
        assert run["completed_at"] is not None

        # Verify database record has terminal status COMPLETED, not left in RUNNING
        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            saved_run = repository.get_run(run["run_id"])
            assert saved_run is not None
            assert saved_run.status == RetentionRunStatus.COMPLETED
            assert saved_run.completed_at is not None

            # Verify RUN_COMPLETED audit event is present
            events = repository.list_audit_events()
            completed_events = [e for e in events if e.run_id == run["run_id"] and e.event_type == RetentionAuditEventType.RUN_COMPLETED]
            assert len(completed_events) == 1

    def test_persisted_policy_overrides_loaded_on_restart(self, db_manager):
        manager = self.make_manager(db_manager)
        manager.update_policy("trace_events", retention_period="14d", confirm=True, actor="ops_user")

        # Create a new manager instance mimicking application reboot
        new_manager = self.make_manager(db_manager)
        policy = new_manager.resolver.get("trace_events")
        assert policy.retention_period == "14d"
        assert policy.updated_by == "ops_user"
        assert policy.updated_at is not None

    def test_overlapping_runs_rejected_by_run_lock(self, db_manager):
        manager = self.make_manager(db_manager)
        assert manager._run_lock.acquire(blocking=False)
        try:
            with pytest.raises(RetentionRunAlreadyInProgress):
                manager.execute(actor="concurrent-tester")
        finally:
            manager._run_lock.release()

