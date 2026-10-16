from __future__ import annotations

from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.logging.application_logging_mixin import ApplicationLoggingMixin


class RetentionGovernanceInput(BaseModel):
    action: str = Field(
        default="summary",
        description=(
            "Action: 'summary' (configured policies, preview dry-run, last completed run, and skip reasons), "
            "'preview' (dry-run expiration preview), or 'runs' (completed retention run history)."
        ),
    )
    run_id: Optional[str] = Field(
        default=None,
        description="Optional retention run ID to inspect specific deleted/skipped outcomes.",
    )


class RetentionGovernanceTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "inspect_retention_governance"
    description: str = (
        "Inspects data retention governance: configured retention policies per data category, "
        "dry-run expiration previews (what WILL expire), completed retention runs (what WAS deleted or archived), "
        "active legal/retention holds, and exact skip reasons (e.g. RETENTION_HOLD, DEPENDENCY_REFERENCED)."
    )
    args_schema: Type[BaseModel] = RetentionGovernanceInput
    retention_manager: Any

    def __init__(self, retention_manager: Any):
        super().__init__(retention_manager=retention_manager)

    def _run(  # pylint: disable=arguments-differ
            self,
            action: str = "summary",
            run_id: Optional[str] = None,
    ) -> str:
        norm = action.strip().lower()
        if run_id:
            run_data = self.retention_manager.get_run(run_id.strip())
            if not run_data:
                return f"Retention run '{run_id}' not found."
            return self._format_run(run_data, header=f"=== Retention Run {run_id} ===")

        if norm == "preview":
            preview_data = self.retention_manager.preview()
            return self._format_run(
                preview_data,
                header="=== Retention Dry-Run Preview (Configured Expiration Forecast) ===",
            )

        status = self.retention_manager.status()
        policies = self.retention_manager.list_policies()
        runs = self.retention_manager.list_runs(limit=5)
        preview_data = self.retention_manager.preview()

        lines = [
            "=== Data Retention Governance Report ===",
            f"Global Enabled: {status.get('enabled')} | Schedule: {status.get('schedule')} | "
            f"Default Dry-Run Mode: {status.get('dry_run')} | Grace Period: {status.get('grace_period')}",
            "\n1. [Configured Retention Policies (What is Retained vs Expired by Rule)]",
        ]
        for p in policies:
            lines.append(
                f"  - {p.get('data_category')} (policy_id={p.get('policy_id')}): "
                f"Period={p.get('retention_period')}, Mode={p.get('retention_mode')}, "
                f"Enabled={p.get('enabled')}, Records={p.get('record_count')}"
            )

        lines.append("\n2. [Dry-Run Expiration Preview (What WILL Expire — Not Yet Deleted)]")
        lines.append(self._format_run(preview_data, header=None))

        completed_non_preview = [r for r in runs if r.get("trigger") != "PREVIEW" and not r.get("dry_run")]
        if completed_non_preview:
            lines.append("\n3. [Last Completed Execution Run (Actual Deletions / Archivals & Skipped Records)]")
            lines.append(self._format_run(completed_non_preview[0], header=None))
        elif runs:
            lines.append("\n3. [Recent Run History]")
            lines.append(self._format_run(runs[0], header=None))
        else:
            lines.append("\n3. [Completed Execution Runs]\n  No destructive retention runs have been executed yet.")

        return "\n".join(lines)

    @staticmethod
    def _format_run(run_data: dict, header: Optional[str] = None) -> str:
        lines: list[str] = []
        if header:
            lines.append(header)
        mode_label = (
            "DRY-RUN PREVIEW (No records modified)"
            if run_data.get("dry_run") else "EXECUTED RUN (Completed changes)"
        )
        lines.append(
            f"  Run ID: {run_data.get('run_id')} | Status: {run_data.get('status')} | "
            f"Trigger: {run_data.get('trigger')} | Mode: {mode_label}"
        )
        for cat in run_data.get("categories") or []:
            skip_parts = [
                f"{sr.get('reason')} (count={sr.get('count')}"
                f"{', detail=' + str(sr.get('detail')) if sr.get('detail') else ''})"
                for sr in (cat.get("skipped_reasons") or [])
            ]
            skip_str = f" | Skip Reasons: {', '.join(skip_parts)}" if skip_parts else ""
            lines.append(
                f"  - Category {cat.get('data_category')} ({cat.get('retention_mode')}): "
                f"Examined={cat.get('examined')}, Eligible={cat.get('eligible')}, "
                f"Deleted={cat.get('deleted')}, Archived={cat.get('archived')}, "
                f"Skipped={cat.get('skipped')}{skip_str}"
            )
        return "\n".join(lines)
