from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, cast

from api.interfaces.scorecard import (
    LifecycleStage,
    ScorecardSnapshotRecord,
    ScorecardSnapshotSummary,
    StrategyScorecardResponse,
)
from src.database.dao.scorecard_snapshot_dao import ScorecardSnapshotDao
from src.database.repositories.base_repository import BaseRepository


class PostgresScorecardSnapshotRepository(BaseRepository[ScorecardSnapshotDao]):

    def save(self, entity: ScorecardSnapshotDao) -> ScorecardSnapshotDao:
        self.database_session.add(entity)
        self.database_session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[ScorecardSnapshotDao]:
        row = (
            self.database_session.query(ScorecardSnapshotDao)
            .filter(ScorecardSnapshotDao.snapshot_id == entity_id)
            .first()
        )
        return cast(Optional[ScorecardSnapshotDao], row)

    def get_all(self) -> List[ScorecardSnapshotDao]:
        rows = (
            self.database_session.query(ScorecardSnapshotDao)
            .order_by(ScorecardSnapshotDao.created_at.desc())
            .limit(100)
            .all()
        )
        return cast(List[ScorecardSnapshotDao], rows)

    def update(self, entity_id: str, entity: ScorecardSnapshotDao) -> None:
        self.save(entity)

    def upsert(self, entity: ScorecardSnapshotDao) -> None:
        existing = self.get(entity.snapshot_id)
        if existing is None:
            self.save(entity)

    def delete(self, entity_id: str) -> None:
        existing = self.get(entity_id)
        if existing is not None:
            self.database_session.delete(existing)
            self.database_session.flush()

    def save_snapshot(self, record: ScorecardSnapshotRecord) -> ScorecardSnapshotRecord:
        card = record.scorecard
        stage_map = {s.stage: s for s in card.stages}
        live = stage_map.get("live")
        oos = stage_map.get("walk_forward_oos")
        backtest = stage_map.get("backtest")
        max_dd = (
            (oos.max_drawdown_pct if oos and oos.max_drawdown_pct is not None else None)
            or (backtest.max_drawdown_pct if backtest else None)
        )
        dao = ScorecardSnapshotDao(
            snapshot_id=record.snapshot_id,
            symbol=card.symbol,
            branch=card.branch,
            commit_hash=card.commit_hash,
            trigger=record.trigger,
            current_stage=card.lifecycle.current_stage.value,
            drifted=card.latest_drift.drifted if card.latest_drift else None,
            live_return_pct=live.return_pct if live else None,
            oos_return_pct=oos.return_pct if oos else None,
            backtest_return_pct=backtest.return_pct if backtest else None,
            max_drawdown_pct=max_dd,
            payload=card.model_dump(mode="json"),
            created_at=datetime.fromisoformat(record.created_at)
            if record.created_at
            else datetime.now(timezone.utc),
        )
        self.save(dao)
        return record

    def get_snapshot(self, snapshot_id: str) -> Optional[ScorecardSnapshotRecord]:
        row = self.get(snapshot_id)
        if row is None:
            return None
        created_at = row.created_at.isoformat() if row.created_at else datetime.now(timezone.utc).isoformat()
        return ScorecardSnapshotRecord(
            snapshot_id=row.snapshot_id,
            trigger=row.trigger if row.trigger in ("manual", "drift_run") else "manual",
            created_at=created_at,
            scorecard=StrategyScorecardResponse.model_validate(row.payload),
        )

    def list_snapshots(
            self,
            symbol: Optional[str] = None,
            limit: int = 50,
    ) -> list[ScorecardSnapshotSummary]:
        query = self.database_session.query(ScorecardSnapshotDao)
        if symbol:
            query = query.filter(ScorecardSnapshotDao.symbol == symbol)
        rows = query.order_by(ScorecardSnapshotDao.created_at.desc()).limit(limit).all()
        summaries: list[ScorecardSnapshotSummary] = []
        for row in rows:
            payload = row.payload if isinstance(row.payload, dict) else {}
            created_at = row.created_at.isoformat() if row.created_at else ""
            try:
                stage = LifecycleStage(row.current_stage)
            except ValueError:
                stage = LifecycleStage.DRAFT
            summaries.append(
                ScorecardSnapshotSummary(
                    snapshot_id=row.snapshot_id,
                    symbol=row.symbol,
                    venue=str(payload.get("venue") or "default"),
                    quote_currency=str(payload.get("quote_currency") or "USD"),
                    branch=row.branch or "main",
                    commit_hash=row.commit_hash,
                    trigger=row.trigger if row.trigger in ("manual", "drift_run") else "manual",
                    current_stage=stage,
                    live_return_pct=row.live_return_pct,
                    oos_return_pct=row.oos_return_pct,
                    backtest_return_pct=row.backtest_return_pct,
                    max_drawdown_pct=row.max_drawdown_pct,
                    drifted=row.drifted,
                    created_at=created_at,
                )
            )
        return summaries
