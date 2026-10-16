from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from src.configuration.retention_config import RetentionConfig
from src.retention.durations import parse_duration
from src.retention.models import DataCategory, RetentionMode, RetentionPolicy

_CATEGORY_BY_KEY = {
    "financial_records": DataCategory.FINANCIAL,
    "orders": DataCategory.FINANCIAL,
    "trades": DataCategory.FINANCIAL,
    "trading_decisions": DataCategory.TRADING_DECISION,
    "trace_events": DataCategory.TRACE,
    "timeline": DataCategory.TRACE,
    "metric_samples": DataCategory.METRICS,
    "metrics": DataCategory.METRICS,
    "runtime_incidents": DataCategory.RUNTIME_ALERT,
    "drift_alerts": DataCategory.RUNTIME_ALERT,
    "experiment_metadata": DataCategory.EXPERIMENT,
    "experiments": DataCategory.EXPERIMENT,
    "experiment_artifacts": DataCategory.EXPERIMENT_ARTIFACT,
    "backtest_reports": DataCategory.REPORT,
    "reports": DataCategory.REPORT,
    "market_datasets": DataCategory.MARKET_DATA,
    "market_data": DataCategory.MARKET_DATA,
    "market_data_buffer": DataCategory.MARKET_DATA_BUFFER,
    "application_logs": DataCategory.APPLICATION_LOG,
    "config_history": DataCategory.CONFIG_HISTORY,
    "cache_buffers": DataCategory.CACHE,
}

DESTRUCTIVE_MODES = {RetentionMode.DELETE, RetentionMode.AGGREGATE_THEN_DELETE}


class RetentionPolicyResolver:
    def __init__(self, config: RetentionConfig):
        self._config = config
        self._overrides: dict[str, dict[str, Any]] = {}
        self._policies: dict[str, RetentionPolicy] = {}
        self._version = ""
        self.rebuild()

    def rebuild(self) -> None:
        policies: dict[str, RetentionPolicy] = {}
        for policy_id, settings in self._config.policies.items():
            merged = settings.model_dump()
            merged.update(self._overrides.get(policy_id, {}))
            policies[policy_id] = self._build_policy(policy_id, merged)
        self._policies = policies
        self._version = self._compute_version(policies)

    def _build_policy(self, policy_id: str, merged: dict[str, Any]) -> RetentionPolicy:
        category = self._resolve_category(policy_id, merged.get("data_category"))
        mode = RetentionMode(merged["retention_mode"])
        period = str(merged["retention_period"])
        parse_duration(period)
        grace = merged.get("grace_period") or self._config.grace_period
        parse_duration(grace)
        return RetentionPolicy(
            policy_id=policy_id,
            data_category=category,
            retention_period=period,
            retention_mode=mode,
            scope=merged.get("scope", "GLOBAL"),
            enabled=bool(merged.get("enabled", True)),
            grace_period=str(grace),
            description=merged.get("description", ""),
            updated_at=merged.get("updated_at"),
            updated_by=merged.get("updated_by"),
        )

    def apply_overrides(self, overrides: dict[str, dict[str, Any]]) -> None:
        for policy_id, data in overrides.items():
            if not isinstance(data, dict):
                continue
            entry = self._overrides.setdefault(policy_id, {})
            if data.get("retention_period") is not None:
                entry["retention_period"] = data["retention_period"]
            if data.get("retention_mode") is not None:
                entry["retention_mode"] = data["retention_mode"]
            if data.get("enabled") is not None:
                entry["enabled"] = bool(data["enabled"])
            if "updated_at" in data:
                entry["updated_at"] = data["updated_at"]
            if "updated_by" in data:
                entry["updated_by"] = data["updated_by"]
        self.rebuild()

    @staticmethod
    def _resolve_category(policy_id: str, raw_category: Optional[str]) -> DataCategory:
        if raw_category:
            try:
                return DataCategory(raw_category)
            except ValueError as exc:
                raise ValueError(f"Unknown data_category '{raw_category}'") from exc
        if policy_id.upper() in DataCategory.__members__:
            return DataCategory(policy_id.upper())
        if policy_id in _CATEGORY_BY_KEY:
            return _CATEGORY_BY_KEY[policy_id]
        raise ValueError(f"Cannot resolve data category for policy '{policy_id}'")

    @staticmethod
    def _compute_version(policies: dict[str, RetentionPolicy]) -> str:
        payload = json.dumps(
            [policies[key].to_dict() for key in sorted(policies)],
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

    @property
    def version(self) -> str:
        return self._version

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def config(self) -> RetentionConfig:
        return self._config

    def policies(self) -> list[RetentionPolicy]:
        return list(self._policies.values())

    def get(self, policy_id: str) -> Optional[RetentionPolicy]:
        return self._policies.get(policy_id)

    def update(
            self,
            policy_id: str,
            *,
            retention_period: Optional[str] = None,
            retention_mode: Optional[str] = None,
            enabled: Optional[bool] = None,
            actor: Optional[str] = None,
            now: Optional[datetime] = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        policy = self._policies.get(policy_id)
        if policy is None:
            raise KeyError(policy_id)

        changes: dict[str, Any] = {}
        if retention_period is not None:
            parse_duration(retention_period)
            changes["retention_period"] = retention_period
        if retention_mode is not None:
            changes["retention_mode"] = RetentionMode(retention_mode).value
        if enabled is not None:
            changes["enabled"] = bool(enabled)
        if not changes:
            return policy.to_dict(), policy.to_dict()

        changes["updated_at"] = now or datetime.now(timezone.utc)
        changes["updated_by"] = actor
        old_value = policy.to_dict()
        self._overrides.setdefault(policy_id, {}).update(changes)
        self.rebuild()
        return old_value, self._policies[policy_id].to_dict()

    @staticmethod
    def requires_confirmation(old: dict[str, Any], new: dict[str, Any]) -> bool:
        old_mode = RetentionMode(old["retention_mode"])
        new_mode = RetentionMode(new["retention_mode"])
        if new_mode in DESTRUCTIVE_MODES and new_mode != old_mode:
            return True
        if new_mode in DESTRUCTIVE_MODES and not old["enabled"] and new["enabled"]:
            return True
        old_delta = parse_duration(old["retention_period"])
        new_delta = parse_duration(new["retention_period"])
        if old_delta is not None and new_delta is not None and new_delta < old_delta:
            return True
        return False
