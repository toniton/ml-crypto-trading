from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session

from src.database.dao.backtest_session_dao import BacktestSessionDao
from src.database.dao.commit_dao import CommitDao
from src.database.dao.experiment_dao import ExperimentDao
from src.database.dao.metric_sample_dao import MetricSampleDao
from src.database.dao.order_dao import OrderDao
from src.database.dao.runtime_incident_dao import RuntimeErrorEventDao, RuntimeIncidentDao
from src.database.dao.timeline_item_dao import TimelineItemDao
from src.database.dao.trade_dao import TradeDao
from src.database.dao.trading_decision_dao import TradingDecisionDao
from src.database.dao.walk_forward_dao import WalkForwardRunDao
from src.recorder.market_data_store import MarketDataStore
from src.retention.models import (
    CategoryOutcome,
    DataCategory,
    RetentionMode,
    RetentionPolicy,
    SkipReason,
)

_LOG_SUFFIX_PATTERN = ("application", "trading", "agent", "audit")


@dataclass
class RetentionContext:
    session: Session
    policy: RetentionPolicy
    now: datetime
    cutoff: Optional[datetime]
    batch_size: int
    dry_run: bool


class RetentionHandler(ABC):
    category: DataCategory

    def evaluate(self, ctx: RetentionContext) -> CategoryOutcome:
        return self._act(ctx, True)

    def execute(self, ctx: RetentionContext) -> CategoryOutcome:
        return self._act(ctx, False)

    def summary(self, _session: Session) -> tuple[Optional[int], Optional[int]]:
        return None, None

    def sync_policy(self, _policy: RetentionPolicy) -> None:
        """Apply the effective policy to the owned resource (config only, no data mutation)."""

    def _base(self, ctx: RetentionContext) -> CategoryOutcome:
        return CategoryOutcome(
            data_category=self.category,
            policy_id=ctx.policy.policy_id,
            retention_mode=ctx.policy.retention_mode,
        )

    def _kept(self, ctx: RetentionContext, examined: int) -> CategoryOutcome:
        outcome = self._base(ctx)
        outcome.examined = examined
        outcome.skipped = examined
        if examined:
            outcome.skipped_reasons.append(SkipReason(reason="KEEP", count=examined))
        return outcome

    def _apply_mode(self, outcome: CategoryOutcome, mode: RetentionMode, count: int) -> None:
        if count <= 0:
            return
        if mode == RetentionMode.AGGREGATE_THEN_DELETE:
            outcome.aggregated += count
            outcome.deleted += count
        elif mode == RetentionMode.ARCHIVE:
            outcome.archived += count
        elif mode == RetentionMode.DELETE:
            outcome.deleted += count

    def _bulk_delete_before(
            self,
            session: Session,
            dao: type,
            timestamp_column,
            cutoff: datetime,
            batch_size: int,
    ) -> int:
        total = 0
        while True:
            rows = session.query(dao.id).filter(timestamp_column < cutoff).limit(batch_size).all()
            if not rows:
                break
            id_values = [row[0] for row in rows]
            deleted = (
                session.query(dao)
                .filter(dao.id.in_(id_values))
                .delete(synchronize_session=False)
            )
            total += deleted
            if deleted < batch_size:
                break
        return total

    @abstractmethod
    def _act(self, ctx: RetentionContext, dry_run: bool) -> CategoryOutcome:
        raise NotImplementedError()


class TableRetentionHandler(RetentionHandler):
    def __init__(self, category: DataCategory, dao: type, timestamp_column):
        self.category = category
        self._dao = dao
        self._timestamp_column = timestamp_column

    def _count(self, session: Session) -> int:
        return session.query(self._dao).count()

    def _count_before(self, session: Session, cutoff: datetime) -> int:
        return session.query(self._dao).filter(self._timestamp_column < cutoff).count()

    def summary(self, session: Session) -> tuple[Optional[int], Optional[int]]:
        return self._count(session), None

    def _act(self, ctx: RetentionContext, dry_run: bool) -> CategoryOutcome:
        examined = self._count(ctx.session)
        if ctx.policy.retention_mode == RetentionMode.KEEP or ctx.cutoff is None:
            return self._kept(ctx, examined)
        outcome = self._base(ctx)
        outcome.examined = examined
        eligible = self._count_before(ctx.session, ctx.cutoff)
        outcome.eligible = eligible
        if dry_run:
            return outcome
        deleted = self._bulk_delete_before(
            ctx.session, self._dao, self._timestamp_column, ctx.cutoff, ctx.batch_size
        )
        self._apply_mode(outcome, ctx.policy.retention_mode, deleted)
        return outcome


class RuntimeAlertHandler(RetentionHandler):
    category = DataCategory.RUNTIME_ALERT

    def _count(self, session: Session) -> int:
        return session.query(RuntimeIncidentDao).count() + session.query(RuntimeErrorEventDao).count()

    def summary(self, session: Session) -> tuple[Optional[int], Optional[int]]:
        return self._count(session), None

    def _act(self, ctx: RetentionContext, dry_run: bool) -> CategoryOutcome:
        examined = self._count(ctx.session)
        if ctx.policy.retention_mode == RetentionMode.KEEP or ctx.cutoff is None:
            return self._kept(ctx, examined)
        outcome = self._base(ctx)
        outcome.examined = examined
        events_eligible = (
            ctx.session.query(RuntimeErrorEventDao)
            .filter(RuntimeErrorEventDao.timestamp < ctx.cutoff)
            .count()
        )
        incidents_eligible = (
            ctx.session.query(RuntimeIncidentDao)
            .filter(RuntimeIncidentDao.first_seen < ctx.cutoff)
            .count()
        )
        outcome.eligible = events_eligible + incidents_eligible
        if dry_run:
            return outcome
        removed_events = self._bulk_delete_before(
            ctx.session, RuntimeErrorEventDao, RuntimeErrorEventDao.timestamp, ctx.cutoff, ctx.batch_size
        )
        removed_incidents = self._bulk_delete_before(
            ctx.session, RuntimeIncidentDao, RuntimeIncidentDao.first_seen, ctx.cutoff, ctx.batch_size
        )
        self._apply_mode(outcome, ctx.policy.retention_mode, removed_events + removed_incidents)
        return outcome


class ReportHandler(RetentionHandler):
    category = DataCategory.REPORT

    def _count(self, session: Session) -> int:
        return session.query(BacktestSessionDao).count() + session.query(WalkForwardRunDao).count()

    def summary(self, session: Session) -> tuple[Optional[int], Optional[int]]:
        return self._count(session), None

    def _collect_report_references(self, session: Session) -> tuple[set[str], set[str]]:
        session_ids: set[str] = set()
        run_ids: set[str] = set()
        for (bindings,) in session.query(ExperimentDao.run_bindings).all():
            for binding in bindings or []:
                if not isinstance(binding, dict):
                    continue
                if binding.get("backtest_session_id"):
                    session_ids.add(binding["backtest_session_id"])
                if binding.get("walk_forward_run_id"):
                    run_ids.add(binding["walk_forward_run_id"])
        return session_ids, run_ids

    def _partition_eligible_reports(
            self, session: Session, cutoff: datetime
    ) -> tuple[list[str], list[str], int]:
        referenced_sessions, referenced_runs = self._collect_report_references(session)
        old_sessions = [
            row[0]
            for row in session.query(BacktestSessionDao.id)
            .filter(BacktestSessionDao.created_at < cutoff)
            .all()
        ]
        old_runs = [
            row[0]
            for row in session.query(WalkForwardRunDao.id)
            .filter(WalkForwardRunDao.created_at < cutoff)
            .all()
        ]
        eligible_sessions = [sid for sid in old_sessions if sid not in referenced_sessions]
        eligible_runs = [rid for rid in old_runs if rid not in referenced_runs]
        skipped = (len(old_sessions) - len(eligible_sessions)) + (len(old_runs) - len(eligible_runs))
        return eligible_sessions, eligible_runs, skipped

    def _act(self, ctx: RetentionContext, dry_run: bool) -> CategoryOutcome:
        examined = self._count(ctx.session)
        if ctx.policy.retention_mode == RetentionMode.KEEP or ctx.cutoff is None:
            return self._kept(ctx, examined)
        outcome = self._base(ctx)
        outcome.examined = examined

        eligible_sessions, eligible_runs, skipped = self._partition_eligible_reports(
            ctx.session, ctx.cutoff
        )
        outcome.skipped = skipped
        outcome.eligible = len(eligible_sessions) + len(eligible_runs)
        if skipped:
            outcome.skipped_reasons.append(SkipReason(reason="DEPENDENCY", count=skipped))
        if dry_run:
            return outcome

        removed = 0
        batch_size = max(1, ctx.batch_size)
        for i in range(0, len(eligible_sessions), batch_size):
            chunk = eligible_sessions[i : i + batch_size]
            removed += (
                ctx.session.query(BacktestSessionDao)
                .filter(BacktestSessionDao.id.in_(chunk))
                .delete(synchronize_session=False)
            )
        for i in range(0, len(eligible_runs), batch_size):
            chunk = eligible_runs[i : i + batch_size]
            removed += (
                ctx.session.query(WalkForwardRunDao)
                .filter(WalkForwardRunDao.id.in_(chunk))
                .delete(synchronize_session=False)
            )
        self._apply_mode(outcome, ctx.policy.retention_mode, removed)
        return outcome


class ExperimentHandler(RetentionHandler):
    category = DataCategory.EXPERIMENT

    def summary(self, session: Session) -> tuple[Optional[int], Optional[int]]:
        return session.query(ExperimentDao).count(), None

    def _act(self, ctx: RetentionContext, _dry_run: bool) -> CategoryOutcome:
        return self._kept(ctx, self.summary(ctx.session)[0] or 0)


class ExperimentArtifactHandler(RetentionHandler):
    category = DataCategory.EXPERIMENT_ARTIFACT
    _COMPACT_KEYS = ("summary", "verdict", "status", "completed_at", "error_message")
    _TERMINAL_STATUSES = ("COMPLETED", "FAILED", "CANCELLED")

    def summary(self, session: Session) -> tuple[Optional[int], Optional[int]]:
        count = session.query(ExperimentDao).filter(ExperimentDao.report.isnot(None)).count()
        return count, None

    def _act(self, ctx: RetentionContext, dry_run: bool) -> CategoryOutcome:
        examined = self.summary(ctx.session)[0] or 0
        if ctx.policy.retention_mode == RetentionMode.KEEP or ctx.cutoff is None:
            return self._kept(ctx, examined)
        outcome = self._base(ctx)
        outcome.examined = examined
        rows = (
            ctx.session.query(ExperimentDao)
            .filter(
                ExperimentDao.report.isnot(None),
                ExperimentDao.created_at < ctx.cutoff,
                ExperimentDao.status.in_(self._TERMINAL_STATUSES),
            )
            .all()
        )
        outcome.eligible = len(rows)
        if dry_run:
            return outcome
        for row in rows:
            report = row.report or {}
            row.report = {key: report[key] for key in self._COMPACT_KEYS if key in report}
        ctx.session.flush()
        self._apply_mode(outcome, ctx.policy.retention_mode, len(rows))
        return outcome


class MarketDataHandler(RetentionHandler):
    category = DataCategory.MARKET_DATA

    def __init__(self, datasets_dir: str = "data/datasets"):
        self._datasets_dir = Path(datasets_dir)

    def _meta_files(self) -> list[Path]:
        if not self._datasets_dir.is_dir():
            return []
        return list(self._datasets_dir.glob("*.meta.json"))

    def summary(self, _session: Session) -> tuple[Optional[int], Optional[int]]:
        files = self._meta_files()
        total_bytes = 0
        for meta in files:
            total_bytes += self._dataset_bytes(meta.stem.replace(".meta", ""))
        return len(files), total_bytes

    def _dataset_bytes(self, dataset_id: str) -> int:
        total = 0
        for suffix in (".csv", ".meta.json"):
            candidate = self._datasets_dir / f"{dataset_id}{suffix}"
            if candidate.is_file():
                total += candidate.stat().st_size
        return total

    def _collect_dataset_references(self, session: Session) -> set[str]:
        references: set[str] = set()
        for (config,) in session.query(BacktestSessionDao.config).all():
            references |= self._extract_dataset_ids(config)
        for (spec,) in session.query(ExperimentDao.spec).all():
            references |= self._extract_dataset_ids(spec)
        for (spec,) in session.query(WalkForwardRunDao.spec).all():
            references |= self._extract_dataset_ids(spec)
        return references

    def _extract_dataset_ids(self, payload) -> set[str]:
        found: set[str] = set()
        if isinstance(payload, dict):
            data_source = payload.get("data_source")
            if isinstance(data_source, dict):
                for key in ("source_id", "dataset_id", "path"):
                    value = data_source.get(key)
                    if isinstance(value, str) and value:
                        found.add(value)
            for value in payload.values():
                found |= self._extract_dataset_ids(value)
        elif isinstance(payload, list):
            for item in payload:
                found |= self._extract_dataset_ids(item)
        return found

    def _act(self, ctx: RetentionContext, dry_run: bool) -> CategoryOutcome:
        examined = len(self._meta_files())
        if ctx.policy.retention_mode == RetentionMode.KEEP or ctx.cutoff is None:
            return self._kept(ctx, examined)
        outcome = self._base(ctx)
        outcome.examined = examined
        references = self._collect_dataset_references(ctx.session)
        cutoff_ts = ctx.cutoff.timestamp()
        eligible: list[str] = []
        skipped = 0
        for meta in self._meta_files():
            dataset_id = meta.stem.replace(".meta", "")
            if dataset_id in references:
                skipped += 1
                continue
            if meta.stat().st_mtime < cutoff_ts:
                eligible.append(dataset_id)
        outcome.eligible = len(eligible)
        outcome.skipped = skipped
        if skipped:
            outcome.skipped_reasons.append(SkipReason(reason="DEPENDENCY", count=skipped))
        outcome.storage_bytes = sum(self._dataset_bytes(dataset_id) for dataset_id in eligible)
        if dry_run:
            return outcome
        removed = 0
        for dataset_id in eligible:
            for suffix in (".csv", ".meta.json"):
                candidate = self._datasets_dir / f"{dataset_id}{suffix}"
                if candidate.is_file():
                    try:
                        candidate.unlink()
                        removed += 1
                    except OSError:
                        pass
        self._apply_mode(outcome, ctx.policy.retention_mode, len(eligible))
        outcome.storage_bytes = outcome.storage_bytes if outcome.deleted or outcome.archived else 0
        return outcome


class ApplicationLogHandler(RetentionHandler):
    category = DataCategory.APPLICATION_LOG

    def __init__(self, log_dir: Optional[str] = None):
        self._log_dir = Path(log_dir or ".")

    def _rotated_log_files(self) -> list[Path]:
        if not self._log_dir.is_dir():
            return []
        files = []
        for candidate in self._log_dir.glob("*.log*"):
            name = candidate.name
            if not any(name.startswith(prefix) for prefix in _LOG_SUFFIX_PATTERN):
                continue
            if candidate.suffix == ".log":
                continue
            files.append(candidate)
        return files

    def summary(self, _session: Session) -> tuple[Optional[int], Optional[int]]:
        files = self._rotated_log_files()
        return len(files), sum(f.stat().st_size for f in files)

    def _act(self, ctx: RetentionContext, dry_run: bool) -> CategoryOutcome:
        files = self._rotated_log_files()
        examined = len(files)
        if ctx.policy.retention_mode == RetentionMode.KEEP or ctx.cutoff is None:
            return self._kept(ctx, examined)
        outcome = self._base(ctx)
        outcome.examined = examined
        cutoff_ts = ctx.cutoff.timestamp()
        eligible = [f for f in files if f.stat().st_mtime < cutoff_ts]
        outcome.eligible = len(eligible)
        outcome.storage_bytes = sum(f.stat().st_size for f in eligible)
        if dry_run:
            return outcome
        reclaimed = 0
        for candidate in eligible:
            reclaimed += candidate.stat().st_size
            candidate.unlink()
        self._apply_mode(outcome, ctx.policy.retention_mode, len(eligible))
        outcome.storage_bytes = reclaimed
        return outcome


class MarketDataBufferHandler(RetentionHandler):
    category = DataCategory.MARKET_DATA_BUFFER

    def __init__(self, store: MarketDataStore):
        self._store = store

    def sync_policy(self, policy: RetentionPolicy) -> None:
        self._store.set_max_age(policy.period_delta())

    def summary(self, _session: Session) -> tuple[Optional[int], Optional[int]]:
        return self._store.size(), None

    def _act(self, ctx: RetentionContext, dry_run: bool) -> CategoryOutcome:
        examined = self._store.size()
        if ctx.policy.retention_mode == RetentionMode.KEEP or ctx.cutoff is None:
            return self._kept(ctx, examined)
        outcome = self._base(ctx)
        outcome.examined = examined
        cutoff_epoch = ctx.cutoff.timestamp()
        outcome.eligible = self._store.count_before(cutoff_epoch)
        if dry_run:
            return outcome
        self._apply_mode(outcome, ctx.policy.retention_mode, self._store.prune(cutoff_epoch))
        return outcome


class KeepHandler(RetentionHandler):
    def __init__(self, category: DataCategory, count_fn: Optional[Callable[[Session], int]] = None):
        self.category = category
        self._count_fn = count_fn

    def summary(self, session: Session) -> tuple[Optional[int], Optional[int]]:
        return (self._count_fn(session) if self._count_fn else 0), None

    def _act(self, ctx: RetentionContext, _dry_run: bool) -> CategoryOutcome:
        return self._kept(ctx, self.summary(ctx.session)[0] or 0)


class RetentionHandlerFactory:
    """Factory for creating standard retention handlers."""

    @classmethod
    def build_default_handlers(
            cls,
            market_data_store: Optional[MarketDataStore] = None,
            datasets_dir: Optional[str] = None,
            log_dir: Optional[str] = None,
    ) -> dict[DataCategory, RetentionHandler]:
        buffer_handler: RetentionHandler = (
            MarketDataBufferHandler(market_data_store)
            if market_data_store is not None
            else KeepHandler(DataCategory.MARKET_DATA_BUFFER)
        )
        return {
            DataCategory.FINANCIAL: KeepHandler(
                DataCategory.FINANCIAL,
                lambda session: session.query(OrderDao).count() + session.query(TradeDao).count(),
            ),
            DataCategory.TRADING_DECISION: KeepHandler(
                DataCategory.TRADING_DECISION,
                lambda session: session.query(TradingDecisionDao).count(),
            ),
            DataCategory.TRACE: TableRetentionHandler(
                DataCategory.TRACE, TimelineItemDao, TimelineItemDao.timestamp
            ),
            DataCategory.METRICS: TableRetentionHandler(
                DataCategory.METRICS, MetricSampleDao, MetricSampleDao.timestamp
            ),
            DataCategory.RUNTIME_ALERT: RuntimeAlertHandler(),
            DataCategory.EXPERIMENT: ExperimentHandler(),
            DataCategory.EXPERIMENT_ARTIFACT: ExperimentArtifactHandler(),
            DataCategory.REPORT: ReportHandler(),
            DataCategory.CONFIG_HISTORY: KeepHandler(
                DataCategory.CONFIG_HISTORY,
                lambda session: session.query(CommitDao).count(),
            ),
            DataCategory.MARKET_DATA: MarketDataHandler(datasets_dir) if datasets_dir else MarketDataHandler(),
            DataCategory.MARKET_DATA_BUFFER: buffer_handler,
            DataCategory.APPLICATION_LOG: ApplicationLogHandler(log_dir),
            DataCategory.CACHE: KeepHandler(DataCategory.CACHE),
        }


build_default_handlers = RetentionHandlerFactory.build_default_handlers
