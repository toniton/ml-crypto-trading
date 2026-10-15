from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from src.retention.durations import RetentionDuration
from src.retention.models import DataCategory, RetentionMode

DEFAULT_RETENTION_CONFIG_PATH = "src/configuration/retention.yaml"


class PolicySettings(BaseModel):
    data_category: Optional[DataCategory] = None
    retention_period: str = "KEEP"
    retention_mode: RetentionMode = RetentionMode.KEEP
    scope: str = "GLOBAL"
    enabled: bool = True
    grace_period: Optional[str] = None
    description: str = ""

    @field_validator("retention_period", "grace_period")
    @classmethod
    def validate_duration_string(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            RetentionDuration.parse(v)
        return v


class DefaultRetentionPolicies:
    """Provider for baseline retention policy configurations."""

    @classmethod
    def get_defaults(cls) -> dict[str, PolicySettings]:
        return {
            "financial_records": PolicySettings(
                data_category=DataCategory.FINANCIAL.value,
                retention_period="KEEP",
                retention_mode=RetentionMode.KEEP.value,
                description="Orders, fills and ledger entries. Never auto-deleted.",
            ),
            "trading_decisions": PolicySettings(
                data_category=DataCategory.TRADING_DECISION.value,
                retention_period="730d",
                retention_mode=RetentionMode.KEEP.value,
                description="Decision snapshots and attribution retained for reproducibility.",
            ),
            "trace_events": PolicySettings(
                data_category=DataCategory.TRACE.value,
                retention_period="90d",
                retention_mode=RetentionMode.ARCHIVE.value,
                description="Detailed lifecycle events for recent investigations.",
            ),
            "metric_samples": PolicySettings(
                data_category=DataCategory.METRICS.value,
                retention_period="30d",
                retention_mode=RetentionMode.DELETE.value,
                description="Raw metric samples; aggregates are preserved by metric definitions.",
            ),
            "runtime_incidents": PolicySettings(
                data_category=DataCategory.RUNTIME_ALERT.value,
                retention_period="180d",
                retention_mode=RetentionMode.AGGREGATE_THEN_DELETE.value,
                description="Drift alerts and runtime incident detail.",
            ),
            "experiment_metadata": PolicySettings(
                data_category=DataCategory.EXPERIMENT.value,
                retention_period="KEEP",
                retention_mode=RetentionMode.KEEP.value,
                description="Experiment definitions, triggers and provenance.",
            ),
            "experiment_artifacts": PolicySettings(
                data_category=DataCategory.EXPERIMENT_ARTIFACT.value,
                retention_period="90d",
                retention_mode=RetentionMode.DELETE.value,
                description="Bulky experiment report payloads; disabled until reviewed.",
            ),
            "backtest_reports": PolicySettings(
                data_category=DataCategory.REPORT.value,
                retention_period="365d",
                retention_mode=RetentionMode.DELETE.value,
                description="Backtest and walk-forward sessions not referenced by experiments.",
            ),
            "market_datasets": PolicySettings(
                data_category=DataCategory.MARKET_DATA.value,
                retention_period="365d",
                retention_mode=RetentionMode.DELETE.value,
                description="Downloaded OHLCV datasets not referenced by retained runs.",
            ),
            "application_logs": PolicySettings(
                data_category=DataCategory.APPLICATION_LOG.value,
                retention_period="30d",
                retention_mode=RetentionMode.DELETE.value,
                description="Rotated application, trading, agent and audit log files.",
            ),
            "config_history": PolicySettings(
                data_category=DataCategory.CONFIG_HISTORY.value,
                retention_period="KEEP",
                retention_mode=RetentionMode.KEEP.value,
                description="VCS commits and blobs referenced by retained records.",
            ),
            "market_data_buffer": PolicySettings(
                data_category=DataCategory.MARKET_DATA_BUFFER.value,
                retention_period="6h",
                retention_mode=RetentionMode.DELETE.value,
                description="In-memory recorded market data used for backtests and recorded-data reads.",
            ),
            "cache_buffers": PolicySettings(
                data_category=DataCategory.CACHE.value,
                retention_period="1d",
                retention_mode=RetentionMode.KEEP.value,
                description="Other rebuildable in-memory buffers.",
            ),
        }


class RetentionConfig(BaseModel):
    enabled: bool = True
    schedule: str = "DAILY"
    dry_run: bool = True
    batch_size: int = 1000
    grace_period: str = "7d"
    policies: dict[str, PolicySettings] = Field(
        default_factory=DefaultRetentionPolicies.get_defaults
    )

    @classmethod
    def default_policies(cls) -> dict[str, PolicySettings]:
        return DefaultRetentionPolicies.get_defaults()

    @classmethod
    def load(cls, path: Optional[str] = None) -> "RetentionConfig":
        config_path = Path(path or DEFAULT_RETENTION_CONFIG_PATH)
        if not config_path.is_file():
            return cls()
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if "retention" in raw and isinstance(raw["retention"], dict):
            raw = raw["retention"]
        return cls.model_validate(raw)


default_policies = RetentionConfig.default_policies
