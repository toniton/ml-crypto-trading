from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.configuration.retention_config import RetentionConfig
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_retention_repository import (
    PostgresRetentionRepository,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.retention.handlers import RetentionContext, RetentionHandler, build_default_handlers
from src.retention.models import (
    CategoryOutcome,
    DataCategory,
    RetentionAuditEvent,
    RetentionAuditEventType,
    RetentionPolicy,
    RetentionRun,
    RetentionRunStatus,
    RetentionTrigger,
    SkipReason,
)
from src.retention.durations import parse_duration
from src.retention.policy_resolver import RetentionPolicyResolver


class RetentionConfirmationRequired(Exception):
    pass


_SCHEDULE_INTERVALS = {
    "HOURLY": timedelta(hours=1),
    "DAILY": timedelta(days=1),
    "WEEKLY": timedelta(weeks=1),
}


class RetentionManager(ApplicationLoggingMixin):
    def __init__(
            self,
            db_manager: DatabaseManager,
            resolver: Optional[RetentionPolicyResolver] = None,
            handlers: Optional[dict[DataCategory, RetentionHandler]] = None,
            config: Optional[RetentionConfig] = None,
    ):
        self._db_manager = db_manager
        self._config = config or RetentionConfig.load()
        self._resolver = resolver or RetentionPolicyResolver(self._config)
        self._handlers = handlers or build_default_handlers()
        self._sync_handlers()

    def _sync_handlers(self) -> None:
        for policy in self._resolver.policies():
            handler = self._handlers.get(policy.data_category)
            if handler is not None:
                handler.sync_policy(policy)

    @property
    def resolver(self) -> RetentionPolicyResolver:
        return self._resolver

    @property
    def config(self) -> RetentionConfig:
        return self._config

    def schedule_interval(self) -> timedelta:
        schedule_str = self._config.schedule.upper()
        if schedule_str in _SCHEDULE_INTERVALS:
            return _SCHEDULE_INTERVALS[schedule_str]
        parsed = parse_duration(self._config.schedule)
        return parsed if parsed is not None else timedelta(days=1)

    def status(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        last_run: Optional[RetentionRun] = None
        total_storage = 0
        with self._db_manager.get_unit_of_work() as uow:
            session = getattr(uow, "session", None)
            if session is not None:
                repository = uow.get_repository(PostgresRetentionRepository)
                runs = repository.list_runs(limit=1)
                last_run = runs[0] if runs else None
                total_storage = sum(
                    (handler.summary(session)[1] or 0) for handler in self._handlers.values()
                )
        return {
            "enabled": self._config.enabled,
            "schedule": self._config.schedule,
            "dry_run": self._config.dry_run,
            "grace_period": self._config.grace_period,
            "next_run_at": (now + self.schedule_interval()).isoformat(),
            "last_run": last_run.to_dict() if last_run else None,
            "total_storage_bytes": total_storage or None,
        }

    def list_policies(self) -> list[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            session = getattr(uow, "session", None)
            policies = []
            for policy in self._resolver.policies():
                record_count: Optional[int] = None
                storage_bytes: Optional[int] = None
                handler = self._handlers.get(policy.data_category)
                if handler is not None and session is not None:
                    record_count, storage_bytes = handler.summary(session)
                policies.append(policy.to_dict(record_count, storage_bytes))
            return policies

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            session = getattr(uow, "session", None)
            if session is None:
                return []
            repository = uow.get_repository(PostgresRetentionRepository)
            return [run.to_dict() for run in repository.list_runs(limit=limit)]

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            session = getattr(uow, "session", None)
            if session is None:
                return None
            repository = uow.get_repository(PostgresRetentionRepository)
            run = repository.get_run(run_id)
            return run.to_dict() if run else None

    def preview(self) -> dict[str, Any]:
        return self._run_once(RetentionTrigger.PREVIEW, dry_run=True).to_dict()

    def execute(self, actor: Optional[str] = None) -> dict[str, Any]:
        run = self._run_once(RetentionTrigger.MANUAL, dry_run=self._config.dry_run, actor=actor)
        return run.to_dict()

    def update_policy(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            policy_id: str,
            *,
            retention_period: Optional[str] = None,
            retention_mode: Optional[str] = None,
            enabled: Optional[bool] = None,
            actor: Optional[str] = None,
            confirm: bool = False,
    ) -> dict[str, Any]:
        policy = self._resolver.get(policy_id)
        if policy is None:
            raise KeyError(policy_id)

        old_value = policy.to_dict()
        candidate = {
            **old_value,
            "retention_period": retention_period if retention_period is not None else old_value["retention_period"],
            "retention_mode": retention_mode if retention_mode is not None else old_value["retention_mode"],
            "enabled": enabled if enabled is not None else old_value["enabled"],
        }
        if self._resolver.requires_confirmation(old_value, candidate) and not confirm:
            raise RetentionConfirmationRequired(
                "This change shortens retention or enables destructive cleanup; confirm to apply."
            )

        old_value, new_value = self._resolver.update(
            policy_id,
            retention_period=retention_period,
            retention_mode=retention_mode,
            enabled=enabled,
        )
        updated_policy = self._resolver.get(policy_id)
        updated_handler = self._handlers.get(updated_policy.data_category) if updated_policy else None
        if updated_handler is not None and updated_policy is not None:
            updated_handler.sync_policy(updated_policy)
        self._record_audit(
            RetentionAuditEvent(
                event_type=RetentionAuditEventType.POLICY_UPDATED,
                policy_id=policy_id,
                actor=actor,
                old_value=old_value,
                new_value=new_value,
                detail="Policy updated",
            )
        )
        self.app_logger.info("Retention policy '%s' updated by %s", policy_id, actor)
        return new_value

    def _run_once(
            self,
            trigger: RetentionTrigger,
            dry_run: bool,
            actor: Optional[str] = None,
    ) -> RetentionRun:
        now = datetime.now(timezone.utc)
        run = RetentionRun(
            status=RetentionRunStatus.RUNNING,
            trigger=trigger,
            dry_run=dry_run,
            policy_version=self._resolver.version,
            started_at=now,
        )
        self.app_logger.info(
            "Retention %s run started (dry_run=%s, actor=%s, version=%s)",
            trigger.value,
            dry_run,
            actor,
            run.policy_version,
        )
        with self._db_manager.get_unit_of_work() as uow:
            session = getattr(uow, "session", None)
            repository = (
                uow.get_repository(PostgresRetentionRepository) if session is not None else None
            )
            if repository is not None:
                repository.save_run(run)
                repository.add_audit_event(
                    RetentionAuditEvent(
                        event_type=RetentionAuditEventType.RUN_STARTED,
                        run_id=run.run_id,
                        actor=actor,
                        detail=f"{trigger.value} run started (dry_run={dry_run})",
                    )
                )

            if not self._config.enabled:
                run.status = RetentionRunStatus.COMPLETED
                run.completed_at = datetime.now(timezone.utc)
                self.app_logger.info("Retention is disabled; run completed with no actions")
                return run

            failures = 0
            for policy in self._resolver.policies():
                outcome = self._evaluate_policy(policy, session, repository, now, dry_run)
                if any(reason.reason == "ERROR" for reason in outcome.skipped_reasons):
                    failures += 1
                run.categories.append(outcome)

            run.completed_at = datetime.now(timezone.utc)
            run.status = RetentionRunStatus.PARTIAL if failures else RetentionRunStatus.COMPLETED
            run.storage_reclaimed_bytes = (
                sum((category.storage_bytes or 0) for category in run.categories) or None
            )

            if repository is not None:
                repository.update_run(run)
                repository.add_audit_event(
                    RetentionAuditEvent(
                        event_type=RetentionAuditEventType.RUN_COMPLETED,
                        run_id=run.run_id,
                        actor=actor,
                        detail=f"{trigger.value} run completed with status {run.status.value}",
                    )
                )
            self.app_logger.info(
                "Retention run %s completed with status %s (reclaimed: %s bytes, failures: %d)",
                run.run_id,
                run.status.value,
                run.storage_reclaimed_bytes or 0,
                failures,
            )
            return run

    def _determine_skip_reason(self, policy: RetentionPolicy, repository) -> Optional[str]:
        if policy.data_category not in self._handlers:
            return "NO_HANDLER"
        if not policy.enabled:
            return "DISABLED"
        if repository is not None and repository.is_category_held(policy.data_category):
            return "LEGAL_HOLD"
        return None

    def _evaluate_policy(
            self,
            policy: RetentionPolicy,
            session,
            repository,
            now: datetime,
            dry_run: bool,
    ) -> CategoryOutcome:
        skip_reason = self._determine_skip_reason(policy, repository)
        if skip_reason is not None:
            return self._skipped(policy, skip_reason)
        if session is None:
            return CategoryOutcome(
                data_category=policy.data_category,
                policy_id=policy.policy_id,
                retention_mode=policy.retention_mode,
            )
        ctx = RetentionContext(
            session=session,
            policy=policy,
            now=now,
            cutoff=policy.cutoff(now),
            batch_size=self._config.batch_size,
            dry_run=dry_run,
        )
        handler = self._handlers[policy.data_category]
        try:
            if not dry_run and hasattr(session, "begin_nested"):
                with session.begin_nested():
                    return handler.execute(ctx)
            return handler.execute(ctx) if not dry_run else handler.evaluate(ctx)
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.exception("Retention execution failed for policy %s", policy.policy_id)
            return self._skipped(policy, "ERROR", detail=str(exc) or "handler failed")

    @staticmethod
    def _skipped(policy: RetentionPolicy, reason: str, detail: Optional[str] = None) -> CategoryOutcome:
        return CategoryOutcome(
            data_category=policy.data_category,
            policy_id=policy.policy_id,
            retention_mode=policy.retention_mode,
            skipped_reasons=[SkipReason(reason=reason, count=0, detail=detail)],
        )

    def _record_audit(self, event: RetentionAuditEvent) -> None:
        with self._db_manager.get_unit_of_work() as uow:
            if getattr(uow, "session", None) is None:
                return
            repository = uow.get_repository(PostgresRetentionRepository)
            repository.add_audit_event(event)
