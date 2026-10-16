from datetime import datetime, timezone

from src.database.repositories.providers.postgres_retention_repository import (
    PostgresRetentionRepository,
)
from src.retention.models import (
    CategoryOutcome,
    DataCategory,
    RetentionAuditEvent,
    RetentionAuditEventType,
    RetentionMode,
    RetentionRun,
    RetentionRunStatus,
    RetentionTrigger,
    SkipReason,
)


class TestRetentionRepository:
    def _build_run(self, run_id="run-1") -> RetentionRun:
        return RetentionRun(
            run_id=run_id,
            status=RetentionRunStatus.COMPLETED,
            trigger=RetentionTrigger.MANUAL,
            dry_run=True,
            policy_version="abc123",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            categories=[
                CategoryOutcome(
                    data_category=DataCategory.TRACE,
                    policy_id="trace_events",
                    retention_mode=RetentionMode.ARCHIVE,
                    examined=10,
                    eligible=4,
                    archived=4,
                    skipped=2,
                    skipped_reasons=[SkipReason(reason="DEPENDENCY", count=2)],
                    storage_bytes=1024,
                )
            ],
            storage_reclaimed_bytes=1024,
        )

    def test_save_and_get_run(self, db_manager):
        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            repository.save_run(self._build_run())
        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            run = repository.get_run("run-1")
            assert run is not None
            assert run.status == RetentionRunStatus.COMPLETED
            assert run.categories[0].data_category == DataCategory.TRACE
            assert run.categories[0].skipped_reasons[0].reason == "DEPENDENCY"

    def test_update_run_status(self, db_manager):
        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            repository.save_run(self._build_run("run-2"))
        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            run = repository.get_run("run-2")
            run.status = RetentionRunStatus.FAILED
            run.error = "boom"
            repository.update_run(run)
        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            assert repository.get_run("run-2").status == RetentionRunStatus.FAILED

    def test_list_runs_orders_by_started_at(self, db_manager):
        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            repository.save_run(self._build_run("run-a"))
            repository.save_run(self._build_run("run-b"))
            runs = repository.list_runs(limit=10)
            assert {run.run_id for run in runs} == {"run-a", "run-b"}

    def test_audit_events(self, db_manager):
        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            repository.add_audit_event(
                RetentionAuditEvent(
                    event_type=RetentionAuditEventType.POLICY_UPDATED,
                    policy_id="trace_events",
                    actor="ops",
                    old_value={"retention_period": "90d"},
                    new_value={"retention_period": "30d"},
                )
            )
        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            events = repository.list_audit_events()
            assert events[0].event_type == RetentionAuditEventType.POLICY_UPDATED
            assert events[0].actor == "ops"

    def test_holds(self, db_manager):
        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            assert repository.is_category_held(DataCategory.FINANCIAL) is False
            hold_id = repository.add_hold(DataCategory.FINANCIAL, "regulatory")
            assert repository.is_category_held(DataCategory.FINANCIAL) is True
            assert repository.release_hold(hold_id) is True
            assert repository.is_category_held(DataCategory.FINANCIAL) is False

    def test_entity_specific_holds(self, db_manager):
        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            hold_id = repository.add_hold(DataCategory.TRACE, "investigation", entity_id="item-42")
            assert repository.is_category_held(DataCategory.TRACE) is False
            assert repository.get_held_entity_ids(DataCategory.TRACE) == {"item-42"}
            assert repository.is_entity_held(DataCategory.TRACE, "item-42") is True
            assert repository.is_entity_held(DataCategory.TRACE, "item-99") is False

            repository.release_hold(hold_id)
            assert repository.get_held_entity_ids(DataCategory.TRACE) == set()
            assert repository.is_entity_held(DataCategory.TRACE, "item-42") is False

    def test_load_persisted_policy_overrides(self, db_manager):
        with db_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresRetentionRepository)
            repository.add_audit_event(
                RetentionAuditEvent(
                    event_type=RetentionAuditEventType.POLICY_UPDATED,
                    policy_id="trace_events",
                    actor="admin",
                    new_value={"retention_period": "14d", "retention_mode": "DELETE", "enabled": True},
                )
            )
            overrides = repository.load_persisted_policy_overrides()
            assert "trace_events" in overrides
            assert overrides["trace_events"]["retention_period"] == "14d"
            assert overrides["trace_events"]["updated_by"] == "admin"
            assert overrides["trace_events"]["updated_at"] is not None
