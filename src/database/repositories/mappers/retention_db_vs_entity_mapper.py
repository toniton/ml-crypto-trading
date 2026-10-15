from __future__ import annotations

from typing import Any, Optional, cast

from src.database.dao.retention_audit_event_dao import RetentionAuditEventDao
from src.database.dao.retention_run_dao import RetentionRunDao
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


class RetentionDBVSEntityMapper:
    @staticmethod
    def map_run_to_db(run: RetentionRun) -> RetentionRunDao:
        return RetentionRunDao(
            id=run.run_id,
            status=run.status.value,
            trigger=run.trigger.value,
            dry_run=run.dry_run,
            policy_version=run.policy_version,
            started_at=run.started_at,
            completed_at=run.completed_at,
            categories=[category.to_dict() for category in run.categories],
            storage_reclaimed_bytes=run.storage_reclaimed_bytes,
            error=run.error,
        )

    @staticmethod
    def update_run_dao(row: RetentionRunDao, run: RetentionRun) -> None:
        row.status = run.status.value
        row.completed_at = run.completed_at
        row.categories = [category.to_dict() for category in run.categories]
        row.storage_reclaimed_bytes = run.storage_reclaimed_bytes
        row.error = run.error

    @classmethod
    def map_run_to_entity(cls, row: RetentionRunDao) -> RetentionRun:
        return RetentionRun(
            run_id=row.id,
            status=RetentionRunStatus(row.status),
            trigger=RetentionTrigger(row.trigger),
            dry_run=bool(row.dry_run),
            policy_version=row.policy_version or "",
            started_at=row.started_at,
            completed_at=row.completed_at,
            categories=[cls.map_outcome_to_entity(item) for item in (row.categories or [])],
            storage_reclaimed_bytes=row.storage_reclaimed_bytes,
            error=row.error,
        )

    @staticmethod
    def map_outcome_to_entity(data: dict[str, Any]) -> CategoryOutcome:
        return CategoryOutcome(
            data_category=DataCategory(data["data_category"]),
            policy_id=data["policy_id"],
            retention_mode=RetentionMode(data["retention_mode"]),
            examined=data.get("examined", 0),
            eligible=data.get("eligible", 0),
            archived=data.get("archived", 0),
            aggregated=data.get("aggregated", 0),
            deleted=data.get("deleted", 0),
            skipped=data.get("skipped", 0),
            skipped_reasons=[
                SkipReason(
                    reason=reason.get("reason", "UNKNOWN"),
                    count=reason.get("count", 0),
                    detail=reason.get("detail"),
                )
                for reason in data.get("skipped_reasons", [])
            ],
            storage_bytes=data.get("storage_bytes"),
        )

    @staticmethod
    def map_audit_to_db(event: RetentionAuditEvent) -> RetentionAuditEventDao:
        return RetentionAuditEventDao(
            id=event.id,
            event_type=event.event_type.value,
            policy_id=event.policy_id,
            actor=event.actor,
            old_value=event.old_value,
            new_value=event.new_value,
            run_id=event.run_id,
            detail=event.detail,
            created_at=event.created_at,
        )

    @staticmethod
    def map_audit_to_entity(row: RetentionAuditEventDao) -> RetentionAuditEvent:
        return RetentionAuditEvent(
            id=row.id,
            event_type=RetentionAuditEventType(row.event_type),
            policy_id=row.policy_id,
            actor=row.actor,
            old_value=cast(Optional[dict[str, Any]], row.old_value),
            new_value=cast(Optional[dict[str, Any]], row.new_value),
            run_id=row.run_id,
            detail=row.detail,
            created_at=row.created_at,
        )
